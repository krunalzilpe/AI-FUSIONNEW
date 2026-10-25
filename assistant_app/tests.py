import json
import numpy as np
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from .models import Document, TextChunk
from .rag import (
    _normalize_document_scope,
    generate_answer,
    retrieve,
)
from .views import ask_question
from .services.embeddings import index_signature


class RetrievalScopeTests(TestCase):
    def test_invalid_scope_never_falls_back_to_all_documents(self):
        with patch("assistant_app.rag.get_chroma_collection") as get_collection:
            self.assertEqual(retrieve("question", documents=["not-an-id"]), [])
        get_collection.assert_not_called()

    def test_scope_normalization_is_strict_and_deduplicated(self):
        self.assertEqual(_normalize_document_scope(["8", 4, "8"]), [4, 8])
        self.assertEqual(_normalize_document_scope(None), None)
        self.assertEqual(_normalize_document_scope([]), [])
        self.assertEqual(_normalize_document_scope(["4", "bad"]), [])
        self.assertEqual(_normalize_document_scope([True]), [])

    def test_retrieval_returns_only_matching_database_source_metadata(self):
        doc = Document.objects.create(
            title="Research source.pdf",
            file="documents/research.pdf",
            file_type="pdf",
            processed=True,
            index_signature=index_signature(),
        )
        chunk = TextChunk.objects.create(
            document=doc,
            chunk_index=2,
            page_number=7,
            text="The perimeter uses a microwave sensor.",
            embedding=[0.1, 0.2],
        )
        collection = Mock()
        collection.count.return_value = 1
        collection.query.return_value = {
            "ids": [[f"doc_{doc.id}_chunk_2"]],
            "metadatas": [[{"doc_id": doc.id, "chunk_index": 2, "page_number": 99, "title": "stale title"}]],
            "documents": [[chunk.text]],
            "distances": [[0.12]],
        }
        embedder = Mock()
        embedder.encode.return_value = np.array([[0.1, 0.2]])

        with patch("assistant_app.rag.get_chroma_collection", return_value=collection), patch(
            "assistant_app.rag.get_embedder", return_value=embedder
        ):
            results = retrieve("Which sensor detects intrusion?", documents=[str(doc.id)])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["chunk"].id, chunk.id)
        self.assertEqual(results[0]["chunk"].document.title, "Research source.pdf")
        self.assertEqual(results[0]["chunk"].page_number, 7)
        self.assertAlmostEqual(results[0]["score"], 0.88)
        self.assertEqual(collection.query.call_args.kwargs["where"], {"doc_id": {"$eq": doc.id}})

    def test_orphaned_or_stale_vector_is_not_a_citation(self):
        Document.objects.create(title="Ready.txt", file="ready.txt", file_type="txt", processed=True, index_signature=index_signature())
        collection = Mock()
        collection.count.return_value = 1
        collection.query.return_value = {
            "ids": [["orphan"]],
            "metadatas": [[{"doc_id": 9001, "chunk_index": 0}]],
            "documents": [["An orphaned passage."]],
            "distances": [[0.1]],
        }
        embedder = Mock()
        embedder.encode.return_value = np.array([[0.1, 0.2]])
        with patch("assistant_app.rag.get_chroma_collection", return_value=collection), patch(
            "assistant_app.rag.get_embedder", return_value=embedder
        ):
            self.assertEqual(retrieve("question"), [])
        collection.query.assert_called_once()

    def test_vector_store_errors_are_not_reported_as_no_evidence(self):
        Document.objects.create(title="Ready.txt", file="ready.txt", file_type="txt", processed=True, index_signature=index_signature())
        collection = Mock()
        collection.count.return_value = 1
        collection.query.side_effect = RuntimeError("vector store offline")
        embedder = Mock()
        embedder.encode.return_value = np.array([[0.1, 0.2]])
        with patch("assistant_app.rag.get_chroma_collection", return_value=collection), patch(
            "assistant_app.rag.get_embedder", return_value=embedder
        ):
            with self.assertRaisesRegex(RuntimeError, "vector store offline"):
                retrieve("question")


@override_settings(LLM_PROVIDER="gemini")
class GroundedAnswerTests(TestCase):
    def setUp(self):
        doc = Document.objects.create(
            title="Research source.pdf",
            file="documents/research.pdf",
            file_type="pdf",
            processed=True,
        )
        self.chunk = TextChunk.objects.create(
            document=doc,
            chunk_index=0,
            page_number=3,
            text="A microwave sensor monitors the perimeter.",
            embedding=[0.1, 0.2],
        )
        self.source = {"chunk": self.chunk, "score": 0.8}

    def test_gemini_answer_must_cite_a_real_numbered_source(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-3.8-flash"}), patch(
            "assistant_app.rag._generate_with_google_genai",
            return_value="A microwave sensor monitors the perimeter [Source 1].",
        ) as generate:
            answer, sources, mode = generate_answer("Which sensor is used?", [self.source])

        self.assertEqual(mode, "gemini")
        self.assertEqual(sources, [self.source])
        self.assertIn("[Source 1]", answer)
        self.assertIn("untrusted input", generate.call_args.args[0])
        self.assertIn("[Source 1 | Research source.pdf | page 3]", generate.call_args.args[0])
        self.assertIn(self.chunk.text, generate.call_args.args[0])

    def test_uncited_or_unknown_citations_are_rejected(self):
        for generated in ("A microwave sensor is used.", "A microwave sensor is used [Source 9]."):
            with self.subTest(generated=generated), patch.dict(
                "os.environ", {"GEMINI_API_KEY": "test-key"}
            ), patch("assistant_app.rag._generate_with_google_genai", return_value=generated):
                answer, sources, mode = generate_answer("Which sensor is used?", [self.source])
            self.assertEqual(mode, "provider_error")
            self.assertIn("verifiable source citations", answer)
            self.assertEqual(sources, [self.source])

    def test_model_can_explicitly_decline_when_passages_are_insufficient(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), patch(
            "assistant_app.rag._generate_with_google_genai", return_value="INSUFFICIENT_EVIDENCE"
        ):
            answer, sources, mode = generate_answer("What was the 2012 revenue?", [self.source])
        self.assertEqual(mode, "no_evidence")
        self.assertIn("do not contain sufficient information", answer)
        self.assertEqual(sources, [])

    def test_low_relevance_results_do_not_call_gemini(self):
        with patch("assistant_app.rag._generate_with_google_genai") as generate:
            answer, sources, mode = generate_answer(
                "Unrelated question?", [{"chunk": self.chunk, "score": 0.01}]
            )
        self.assertEqual(mode, "no_evidence")
        self.assertEqual(sources, [])
        self.assertIn("do not contain sufficient information", answer)
        generate.assert_not_called()


class AskQuestionViewTests(TestCase):
    def setUp(self):
        self.client.get("/")
        self.doc = Document.objects.create(title="Ready.txt", file="ready.txt", file_type="txt", processed=True,
                                           workspace_key="guest:" + self.client.session["workspace_id"], index_signature=index_signature())

    def test_invalid_falsy_scope_is_not_converted_to_all_documents(self):
        with patch("assistant_app.views.retrieve", return_value=[]) as retrieval, patch(
            "assistant_app.views.generate_answer",
            return_value=("No evidence.", [], "no_evidence"),
        ):
            response = self.client.post("/ask/", data=json.dumps({"question": "Which sensor is used?", "documents": 0}), content_type="application/json")

        self.assertEqual(response.status_code, 400)
        retrieval.assert_not_called()

    def test_retrieval_failure_is_reported_as_service_error(self):
        with patch("assistant_app.views.retrieve", side_effect=RuntimeError("offline")):
            response = self.client.post("/ask/", data=json.dumps({"question": "Which sensor is used?", "documents": [self.doc.id]}), content_type="application/json")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(json.loads(response.content)["success"])

