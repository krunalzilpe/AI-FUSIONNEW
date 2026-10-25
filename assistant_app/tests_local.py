import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError

from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from .middleware import RequestLimitMiddleware
from .models import Document, TextChunk
from .services.generation import generate_answer, generate_chat_answer
from .services.local_llm import LocalModelError, generate


@override_settings(LLM_PROVIDER="local")
class LocalGenerationTests(TestCase):
    def test_chat_without_api_credentials_never_calls_google(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}), patch(
            "assistant_app.services.generation.generate_local", return_value="New Delhi is the capital of India."
        ) as local, patch("assistant_app.services.generation._generate_with_google_genai") as google:
            answer, mode = generate_chat_answer("Capital of India?")
        self.assertEqual(mode, "chat")
        self.assertIn("New Delhi", answer)
        local.assert_called_once()
        google.assert_not_called()

    def test_local_document_answers_still_need_valid_citations(self):
        doc = Document.objects.create(title="chapter.txt", file="chapter.txt", file_type="txt")
        chunk = TextChunk.objects.create(document=doc, chunk_index=0, text="Plants use sunlight for photosynthesis.")
        results = [{"chunk": chunk, "score": 0.9}]
        with patch("assistant_app.services.generation.generate_local", return_value="Plants use sunlight [Source 1]."):
            answer, sources, mode = generate_answer("What do plants use?", results)
        self.assertEqual(mode, "local")
        self.assertEqual(sources, results)
        with patch("assistant_app.services.generation.generate_local", return_value="Invented claim [Source 99]."):
            _, sources, mode = generate_answer("What do plants use?", results)
        self.assertEqual(mode, "provider_error")

    def test_local_failure_does_not_fall_back_to_billable_provider(self):
        with patch("assistant_app.services.generation.generate_local", side_effect=LocalModelError("Start the local model.")), patch(
            "assistant_app.services.generation._generate_with_google_genai"
        ) as google:
            answer, mode = generate_chat_answer("Hi")
        self.assertEqual(mode, "provider_error")
        self.assertIn("local model", answer)
        google.assert_not_called()

    def test_default_chat_without_documents_and_retry_keep_the_same_answer(self):
        cache.clear()
        payload = {"question": "Explain gravity simply.", "request_id": str(uuid.uuid4())}
        with patch("assistant_app.views.generate_chat_answer", return_value=("Gravity attracts objects.", "chat")) as chat, patch("assistant_app.views.retrieve") as retrieval:
            first = self.client.post("/ask/", json.dumps(payload), content_type="application/json")
            second = self.client.post("/ask/", json.dumps(payload), content_type="application/json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(first.json()["query_metadata"]["chat_mode"], "general")
        self.assertEqual(first.json()["query_metadata"]["provider"], "local")
        chat.assert_called_once()
        retrieval.assert_not_called()

    def test_empty_selection_chats_instead_of_searching_all_documents(self):
        with patch("assistant_app.views.generate_chat_answer", return_value=("Hello.", "chat")), patch("assistant_app.views.retrieve") as retrieval:
            response = self.client.post("/ask/", json.dumps({"question": "Hello", "documents": []}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"], [])
        retrieval.assert_not_called()

    def test_malformed_modes_and_scopes_are_rejected(self):
        for extra in ({"chat_mode": []}, {"documents": [True]}, {"documents": 0}, {"documents": [10**100]}):
            with self.subTest(extra=extra), patch("assistant_app.views.generate_chat_answer") as chat:
                response = self.client.post("/ask/", json.dumps({"question": "Hi", **extra}), content_type="application/json")
                self.assertEqual(response.status_code, 400)
                chat.assert_not_called()

    def test_actual_media_file_is_not_public_even_in_debug_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "documents" / "private.txt"
            target.parent.mkdir()
            target.write_text("Private content", encoding="utf8")
            with override_settings(DEBUG=True, MEDIA_ROOT=directory):
                response = self.client.get("/media/documents/private.txt")
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(b"Private content", response.content)

    def test_dashboard_nonce_matches_its_script_policy(self):
        response = self.client.get("/")
        nonce = response.wsgi_request.csp_nonce
        self.assertIn(f"'nonce-{nonce}'", response["Content-Security-Policy"])
        self.assertContains(response, f'nonce="{nonce}"')
        self.assertIn("object-src 'none'", response["Content-Security-Policy"])
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")


class LocalTransportTests(SimpleTestCase):
    def test_connection_failure_has_actionable_message_without_raw_details(self):
        with patch("assistant_app.services.local_llm.urlopen", side_effect=URLError("private transport details")):
            with self.assertRaises(LocalModelError) as failure:
                generate("Hello")
        self.assertIn("try again", str(failure.exception))
        self.assertNotIn("private transport", str(failure.exception))

    def test_empty_and_malformed_model_responses_are_errors(self):
        for payload in ({}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = json.dumps(payload).encode()
            with self.subTest(payload=payload), patch("assistant_app.services.local_llm.urlopen", return_value=response):
                with self.assertRaises(LocalModelError):
                    generate("Hello")


@override_settings(RATE_LIMIT_ENABLED=True, CHAT_REQUESTS_PER_MINUTE=2)
class RequestLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_repeated_requests_are_limited_without_affecting_page_loads(self):
        middleware = RequestLimitMiddleware(lambda request: HttpResponse("ok"))
        factory = RequestFactory()
        self.assertEqual(middleware(factory.post("/ask/")).status_code, 200)
        self.assertEqual(middleware(factory.post("/ask/")).status_code, 200)
        limited = middleware(factory.post("/ask/"))
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited["Retry-After"], "60")
        self.assertEqual(middleware(factory.get("/")).status_code, 200)
        self.assertEqual(middleware(factory.post("/ask/", REMOTE_ADDR="127.0.0.2")).status_code, 200)
