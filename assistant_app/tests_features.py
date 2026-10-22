import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from .models import ChatMessage, Conversation, Document, TextChunk
from .rag import process_document, retrieve, split_text, extract_pages
from .services.embeddings import index_signature
from .services.queries import understand_query
from .test_fixtures import pdf_bytes


class WorkspaceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.get("/")
        self.key = "guest:" + self.client.session["workspace_id"]
        self.doc = Document.objects.create(workspace_key=self.key, title="source.pdf", file="documents/source.pdf", file_type="pdf",
                                           processed=True, status="ready", index_signature=index_signature())
        self.chunk = TextChunk.objects.create(document=self.doc, chunk_index=0, page_number=3, text="Budget: 750000 rupees.")
        self.other = Client()
        self.other.get("/")

    def post(self, url="/ask/", **data):
        return self.client.post(url, json.dumps(data), content_type="application/json")

    def test_other_session_cannot_list_query_delete_or_open_document(self):
        self.assertEqual(self.other.get("/documents/").json()["documents"], [])
        for path in [f"/document/{self.doc.id}/delete/", f"/document/{self.doc.id}/reindex/", f"/document/{self.doc.id}/summary/"]:
            self.assertEqual(self.other.post(path).status_code, 404)
        self.assertEqual(self.other.get(f"/document/{self.doc.id}/source/").status_code, 404)
        result = self.other.post("/ask/", json.dumps({"question":"Budget?", "documents":[self.doc.id]}), content_type="application/json")
        self.assertEqual(result.status_code, 404)

    def test_unowned_legacy_data_is_preserved_and_hidden(self):
        old = Document.objects.create(title="legacy.txt", file="legacy.txt", file_type="txt")
        self.assertNotIn(old.id, [d["id"] for d in self.client.get("/documents/").json()["documents"]])
        self.assertTrue(Document.objects.filter(id=old.id).exists())

    def test_invalid_json_and_non_string_questions_do_not_crash(self):
        for payload in ['[]', 'null', 'oops', '{"question":123}', '{"question":null}', '{"question":""}']:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/ask/", payload, content_type="application/json").status_code, 400)

    def test_empty_and_malformed_selection_never_searches_all_documents(self):
        for selection in [[], 0, [True], ["bad"], [self.doc.id, "bad"]]:
            with self.subTest(selection=selection), patch("assistant_app.views.retrieve") as retrieval:
                self.assertEqual(self.post(question="Budget?", documents=selection).status_code, 400)
                retrieval.assert_not_called()

    def make_turn(self, request_id=None):
        with patch("assistant_app.views.retrieve", return_value=[{"chunk": self.chunk, "score":0.8}]), patch(
            "assistant_app.views.generate_answer", return_value=("Budget is 750000 [Source 1].", [{"chunk": self.chunk, "score":0.8}], "gemini")
        ):
            response = self.post(question="Budget?", documents=[self.doc.id], **({"request_id":request_id} if request_id else {}))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_history_keeps_exact_sources_and_explicit_roles(self):
        turn = self.make_turn()
        loaded = self.client.get(f"/conversation/{turn['conversation_id']}/").json()
        self.assertEqual(loaded["turns"][0]["sources"], turn["sources"])
        self.assertEqual([m["role"] for m in loaded["messages"]], ["user", "assistant"])
        self.assertEqual(turn["sources"][0]["page"], 3)
        self.assertEqual(turn["sources"][0]["title"], "source.pdf")
        self.assertEqual(turn["sources"][0]["text"], self.chunk.text)
        self.assertTrue(turn["sources"][0]["url"].endswith("#page=3"))

    def test_txt_citations_never_invent_pdf_page_numbers(self):
        self.doc.file_type = "txt"; self.doc.save()
        turn = self.make_turn()
        self.assertIsNone(turn["sources"][0]["page"])
        self.assertNotIn("#page", turn["sources"][0]["url"])

    def test_deleted_document_keeps_history_passage_without_a_broken_open_action(self):
        turn = self.make_turn()
        self.doc.delete()
        history = self.client.get(f"/conversation/{turn['conversation_id']}/").json()
        saved = history["turns"][0]["sources"][0]
        self.assertEqual(saved["text"], self.chunk.text)
        self.assertIsNone(saved["url"])
        self.assertTrue(saved["unavailable"])

    def test_other_session_cannot_access_modify_or_clear_history(self):
        turn = self.make_turn(); conversation_id = turn["conversation_id"]
        self.assertEqual(self.other.get("/conversations/").json()["conversations"], [])
        self.assertEqual(self.other.get(f"/conversation/{conversation_id}/").status_code, 404)
        for action in ["delete", "clear", "rename"]:
            self.assertEqual(self.other.post(f"/conversation/{conversation_id}/{action}/").status_code, 404)
        self.other.post("/history/clear/")
        self.assertTrue(ChatMessage.objects.filter(pk=turn["id"]).exists())

    def test_same_request_id_is_idempotent(self):
        request_id = str(uuid.uuid4()); turn = self.make_turn(request_id)
        with patch("assistant_app.views.retrieve") as retrieve_again:
            repeated = self.post(question="Budget?", documents=[self.doc.id], request_id=request_id).json()
        self.assertEqual(turn["id"], repeated["id"])
        self.assertEqual(ChatMessage.objects.count(), 1)
        retrieve_again.assert_not_called()

    def test_request_id_cannot_reuse_an_answer_for_a_different_question_or_scope(self):
        request_id = str(uuid.uuid4()); self.make_turn(request_id)
        response = self.post(question="Different question?", documents=[self.doc.id], request_id=request_id)
        self.assertEqual(response.status_code, 409)
        response = self.post(question="Budget?", documents=[], request_id=request_id)
        self.assertEqual(response.status_code, 409)

    def test_authenticated_users_also_have_separate_ownership(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username="researcher", password="test-only-password")
        self.other.force_login(user)
        self.assertEqual(self.other.get("/documents/").json()["documents"], [])
        self.assertEqual(self.other.get(f"/document/{self.doc.id}/source/").status_code, 404)
        Document.objects.create(workspace_key=f"user:{user.pk}", title="personal.txt", file="personal.txt", file_type="txt")
        self.assertEqual(len(self.other.get("/documents/").json()["documents"]), 1)
        self.assertEqual(len(self.client.get("/documents/").json()["documents"]), 1)

    def test_followup_always_retrieves_again(self):
        turn = self.make_turn()
        with patch("assistant_app.views.retrieve", return_value=[]) as retrieval:
            response = self.post(question="Explain that in simple Hindi", documents=[self.doc.id], conversation_id=turn["conversation_id"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("Budget?", retrieval.call_args.kwargs["query_info"]["followup_context"])
        self.assertEqual(response.json()["mode"], "no_evidence")

    def test_rename_clear_and_delete_conversation(self):
        turn = self.make_turn(); conversation_id = turn["conversation_id"]
        self.assertEqual(self.post(f"/conversation/{conversation_id}/rename/", title="Budget review").status_code, 200)
        self.assertEqual(Conversation.objects.get(pk=conversation_id).title, "Budget review")
        self.post(f"/conversation/{conversation_id}/clear/")
        self.assertEqual(ChatMessage.objects.count(), 0)
        self.post(f"/conversation/{conversation_id}/delete/")
        self.assertFalse(Conversation.objects.filter(pk=conversation_id).exists())

    def test_processing_and_model_mismatch_are_distinct_from_no_evidence(self):
        self.doc.index_signature = "old-model"; self.doc.save()
        response = self.post(question="Budget?", documents=[self.doc.id])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["mode"], "processing")

    def test_no_public_media_route(self):
        self.assertEqual(self.client.get("/media/documents/source.pdf").status_code, 404)

    def test_csrf_protection_is_enforced(self):
        protected = Client(enforce_csrf_checks=True)
        self.assertEqual(protected.post("/upload/").status_code, 403)
        protected.get("/")
        token = protected.cookies["csrftoken"].value
        self.assertEqual(protected.post("/profile/", json.dumps({"display_name":"Krunal"}), content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code, 200)


@override_settings(RAG_ASYNC=False)
class IngestionTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.temp.name)
        self.settings_override.enable()
        self.client.get("/")
        self.collection = Mock()
        self.model = Mock()
        self.model.encode.side_effect = lambda rows, **kwargs: np.ones((len(rows), 4))
        self.patches = [patch("assistant_app.rag.get_embedder", return_value=self.model), patch("assistant_app.rag.get_chroma_collection", return_value=self.collection), patch("assistant_app.rag.delete_document_vectors")]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in self.patches: item.stop()
        self.settings_override.disable()
        self.temp.cleanup()

    def upload(self, name, content):
        return self.client.post("/upload/", {"document": SimpleUploadedFile(name, content)})

    def test_pdf_upload_preserves_physical_pages_including_blanks(self):
        response = self.upload("known.pdf", pdf_bytes([None, "Budget is 750000 rupees.", "Deadline is December 15."]))
        self.assertEqual(response.status_code, 202)
        doc = Document.objects.get(pk=response.json()["document"]["id"])
        self.assertTrue(doc.processed)
        self.assertEqual(doc.page_count, 3)
        self.assertEqual(list(doc.chunks.values_list("page_number", flat=True)), [2, 3])
        metadata = self.collection.upsert.call_args.kwargs["metadatas"]
        self.assertEqual([m["page_number"] for m in metadata], [2, 3])

    def test_txt_upload_and_duplicate_do_not_recompute_embeddings(self):
        content = "River levels are measured using ultrasonic sensors.".encode()
        first = self.upload("sensors.txt", content).json()
        second = self.upload("renamed.txt", content).json()
        self.assertEqual(first["document"]["id"], second["document"]["id"])
        self.assertTrue(second["duplicate"])
        self.model.encode.assert_called_once()

    def test_duplicate_content_is_allowed_in_separate_workspaces(self):
        self.upload("a.txt", b"Ultrasonic sensors measure river levels.")
        other = Client(); other.get("/")
        other.post("/upload/", {"document":SimpleUploadedFile("a.txt", b"Ultrasonic sensors measure river levels.")})
        self.assertEqual(Document.objects.count(), 2)

    def test_invalid_types_empty_files_and_bad_pdf_headers(self):
        for name, content in [("evil.html", b"<script>"), ("empty.txt", b""), ("fake.pdf", b"Not a PDF")]:
            self.assertEqual(self.upload(name, content).status_code, 400)
        self.assertEqual(Document.objects.count(), 0)

    def test_oversized_file_is_rejected(self):
        with patch("assistant_app.views.MAX_FILE_SIZE", 10):
            self.assertEqual(self.upload("large.txt", b"a" * 11).status_code, 400)

    def test_scanned_pdf_records_processing_failure_with_ocr_explanation(self):
        response = self.upload("scan.pdf", pdf_bytes([None])).json()
        self.assertEqual(response["document"]["status"], "failed")
        self.assertIn("OCR", response["document"]["error"])
        self.model.encode.assert_not_called()

    def test_malformed_pdf_and_non_utf8_txt_fail_without_stack_traces(self):
        for name, content in [("bad.pdf", b"%PDF-1.7\ncorrupt"), ("bad.txt", b"\xff\xfe\x00")]:
            response = self.upload(name, content).json()
            self.assertEqual(response["document"]["status"], "failed")
            self.assertNotIn("Traceback", response["document"]["error"])

    def test_source_route_serves_the_original_file_after_ownership_check(self):
        content = pdf_bytes(["Budget is 750000 rupees."])
        data = self.upload("source.pdf", content).json()
        response = self.client.get(data["document"]["url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(b"".join(response.streaming_content), content)

    def test_delete_removes_file_and_vectors_and_failure_is_not_swallowed(self):
        data = self.upload("delete.txt", b"A document to delete.").json()
        doc = Document.objects.get(pk=data["document"]["id"]); path = Path(doc.file.path)
        with patch("assistant_app.services.vectorstore.delete_document_vectors", side_effect=RuntimeError("offline")):
            self.assertEqual(self.client.post(f"/document/{doc.id}/delete/").status_code, 503)
        self.assertTrue(path.exists()); self.assertTrue(Document.objects.filter(id=doc.id).exists())
        with patch("assistant_app.services.vectorstore.delete_document_vectors") as cleanup:
            self.assertEqual(self.client.post(f"/document/{doc.id}/delete/").status_code, 200)
        cleanup.assert_called_once_with(doc.id)
        self.assertFalse(path.exists()); self.assertFalse(Document.objects.filter(id=doc.id).exists())

    def test_processing_is_idempotent_for_unchanged_model(self):
        data = self.upload("again.txt", b"A document with a known fact.").json()
        doc = Document.objects.get(pk=data["document"]["id"])
        process_document(doc)
        self.model.encode.assert_called_once()


class QueryAndGenerationTests(TestCase):
    def test_response_language_instruction_does_not_dilute_the_factual_query(self):
        original = "Project ka budget kitna hai? Roman Hinglish me jawab do."
        info = understand_query(original)
        self.assertEqual(info["original"], original)
        self.assertEqual(info["variants"][0], "Project ka budget kitna hai?")
        self.assertIn(original, info["variants"])

    def test_model_configuration_changes_cannot_query_an_old_index(self):
        doc = Document.objects.create(title="old.txt", file="old.txt", file_type="txt", processed=True, index_signature=index_signature())
        with override_settings(EMBEDDING_MODEL="same-dimension-but-different-model"), patch("assistant_app.rag.get_chroma_collection") as collection:
            self.assertEqual(retrieve("Budget?", [doc.id]), [])
        collection.assert_not_called()

    def test_page_detection_handles_hindi_marathi_and_devanagari_digits(self):
        for question in ["Page 3 par kya explain kiya hai?", "पृष्ठ ३ पर क्या है?", "पान ३ वर काय आहे?"]:
            self.assertEqual(understand_query(question)["page"], 3)

    def test_language_hints_and_original_query_are_preserved(self):
        samples = [("Bhai, is PDF me kya likha hai?", "Hinglish"), ("इसका सारांश हिंदी में दें", "Hindi / Devanagari"), ("मराठीत सारांश सांगा", "Marathi"), ("What is the budget?", "Auto / English")]
        for question, language in samples:
            info = understand_query(question)
            self.assertEqual(info["original"], question); self.assertEqual(info["language_hint"], language)

    def test_chunking_cannot_loop_on_invalid_parameters(self):
        for size, overlap in [(0,0), (100,100), (100,-1)]:
            with self.assertRaises(ValueError): split_text("hello", size, overlap)

    def test_chunks_preserve_unicode_and_do_not_duplicate(self):
        text = "नदीची पातळी मोजण्यासाठी सेन्सर वापरले जातात. " * 30
        chunks = split_text(text, 180, 30)
        self.assertTrue(chunks)
        self.assertEqual(len(chunks), len(set(chunks)))
        self.assertTrue(all(len(c) <= 180 for c in chunks))

    def test_api_errors_are_not_exposed_as_no_evidence_or_secrets(self):
        from .rag import generate_answer
        doc = Document.objects.create(title="known.pdf", file="known.pdf", file_type="pdf")
        chunk = TextChunk.objects.create(document=doc, chunk_index=0, page_number=2, text="Budget 750000.")
        with patch.dict("os.environ", {"GEMINI_API_KEY":"test-secret"}), patch("assistant_app.rag._generate_with_google_genai", side_effect=RuntimeError("test-secret private prompt")):
            answer, sources, mode = generate_answer("Budget?", [{"chunk":chunk,"score":0.9}])
        self.assertEqual(mode, "provider_error"); self.assertTrue(sources)
        self.assertNotIn("test-secret", answer); self.assertNotIn("private prompt", answer)

    def test_missing_credentials_still_returns_honest_evidence(self):
        from .rag import generate_answer
        doc = Document.objects.create(title="known.txt", file="known.txt", file_type="txt")
        chunk = TextChunk.objects.create(document=doc, chunk_index=0, text="Budget 750000.")
        with patch.dict("os.environ", {"GEMINI_API_KEY":""}), patch("assistant_app.rag._generate_with_google_genai") as generate:
            answer, sources, mode = generate_answer("Budget?", [{"chunk":chunk,"score":0.9}])
        self.assertEqual(mode, "retrieval_only"); self.assertTrue(sources); generate.assert_not_called()

    def test_quota_error_is_reported_as_api_failure_with_original_evidence(self):
        from .rag import generate_answer
        doc = Document.objects.create(title="known.txt", file="known.txt", file_type="txt")
        chunk = TextChunk.objects.create(document=doc, chunk_index=0, text="Budget 750000.")
        failure = RuntimeError("private-error-details")
        failure.code = 429
        with patch.dict("os.environ", {"GEMINI_API_KEY":"test-secret"}), patch("assistant_app.rag._generate_with_google_genai", side_effect=failure):
            answer, sources, mode = generate_answer("Budget?", [{"chunk":chunk, "score":0.9}])
        self.assertEqual(mode, "provider_error")
        self.assertIn("quota", answer)
        self.assertNotIn("private-error-details", answer)
        self.assertEqual(sources[0]["chunk"].text, "Budget 750000.")
