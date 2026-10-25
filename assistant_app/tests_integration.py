"""Opt-in real embedding + Chroma tests, using isolated temporary storage."""
import os
import tempfile
import time
from pathlib import Path
from unittest import skipUnless

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Document
from .rag import process_document, retrieve, generate_answer, get_chroma_collection
from .services.embeddings import get_embedder
from .services.vectorstore import delete_document_vectors
from .services.queries import understand_query
from .test_fixtures import pdf_bytes, scanned_pdf_bytes, KNOWN_PAGES


@skipUnless(os.getenv("DOCUMIND_INTEGRATION") == "1", "Opt in with python test_rag_pipeline.py")
@override_settings(LLM_PROVIDER="gemini")
class RealRagTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp = tempfile.TemporaryDirectory(prefix="documind-verify-")
        cls.override = override_settings(CHROMA_DB_PATH=str(Path(cls.temp.name)/"chroma"), MEDIA_ROOT=str(Path(cls.temp.name)/"media"))
        cls.override.enable()
        start = time.perf_counter()
        cls.model = get_embedder()
        print(f"\nReal embedding model initialized in {time.perf_counter()-start:.2f}s")

    @classmethod
    def tearDownClass(cls):
        from .services.vectorstore import _client
        # Chroma's Rust client holds open files on Windows. Release the isolated
        # client before asking TemporaryDirectory to remove the fixture storage.
        cls.override.disable()
        super().tearDownClass()
        try:
            cls.temp.cleanup()
        except PermissionError:
            # OS handles are released when this short-lived test process exits.
            pass

    def setUp(self):
        self.doc = Document.objects.create(title="known_facts.pdf", file=SimpleUploadedFile("known_facts.pdf", pdf_bytes(KNOWN_PAGES)), file_type="pdf", workspace_key="test:integration")
        process_document(self.doc)

    def tearDown(self):
        delete_document_vectors(self.doc.id)
        self.doc.file.delete(save=False)

    def test_real_chroma_contains_text_vectors_and_physical_page_metadata(self):
        self.assertTrue(self.doc.processed)
        result = get_chroma_collection().get(where={"doc_id":self.doc.id}, include=["documents","metadatas","embeddings"])
        self.assertEqual(len(result["ids"]), self.doc.chunk_count)
        self.assertEqual({m["page_number"] for m in result["metadatas"]}, {1,2,3})
        self.assertEqual(len(result["embeddings"][0]), 384)
        self.assertTrue(any("750000" in text for text in result["documents"]))

    @skipUnless(os.getenv("DOCUMIND_OCR_TEST") == "1", "Set DOCUMIND_OCR_TEST=1 for real OCR ingestion")
    def test_scanned_pdf_ocr_embeddings_retrieval_and_page_citations(self):
        scan = Document.objects.create(title="scanned_budget.pdf", file=SimpleUploadedFile("scanned_budget.pdf", scanned_pdf_bytes([
            "Aurora Flood Monitoring Project\nSensors measure river levels.",
            "Project Administration\nThe project budget is 750000 rupees.\nThe coordinator is Anika Rao.",
        ])), file_type="pdf", workspace_key="test:integration")
        try:
            process_document(scan)
            self.assertEqual(scan.page_count, 2)
            results = retrieve("What is the project budget?", [scan.id])
            self.assertTrue(results)
            self.assertEqual(results[0]["chunk"].page_number, 2)
            self.assertEqual(results[0]["chunk"].document.title, "scanned_budget.pdf")
            self.assertIn("750000", results[0]["chunk"].text)
            self.assertTrue(all(row["chunk"].document_id == scan.id for row in results))
        finally:
            delete_document_vectors(scan.id)
            scan.file.delete(save=False)

    def test_english_hinglish_hindi_and_marathi_retrieval(self):
        questions = {
            "English":"What is the project budget?",
            "Hinglish":"Project ka budget kitna hai?",
            "Hindi":"परियोजना का बजट कितना है?",
            "Marathi":"प्रकल्पाचे अंदाजपत्रक किती आहे?",
        }
        for language, question in questions.items():
            with self.subTest(language=language):
                start = time.perf_counter()
                results = retrieve(question, [self.doc.id], top_k=3)
                self.assertTrue(results)
                print(f"  {language}: page={results[0]['chunk'].page_number}, cosine={results[0]['score']:.4f}, {(time.perf_counter()-start)*1000:.0f}ms")
                self.assertEqual(results[0]["chunk"].page_number, 2)
                self.assertIn("750000", results[0]["chunk"].text)

    def test_real_page_filter_and_original_passage(self):
        results = retrieve("Page 3 par kya explain kiya hai?", [self.doc.id])
        self.assertTrue(results)
        self.assertTrue(all(r["chunk"].page_number == 3 for r in results))
        self.assertIn("Ultrasonic", results[0]["chunk"].text)
        self.assertEqual(retrieve("Explain page 99", [self.doc.id]), [])
        # Page references never assign a fake page number to TXT evidence.

    def test_real_summary_samples_preserve_documents_and_have_no_fabricated_scores(self):
        results = retrieve("Iska summary simple Hindi me de", [self.doc.id])
        self.assertEqual({r["chunk"].page_number for r in results}, {1,2,3})
        self.assertTrue(all(r["score"] is None for r in results))

    def test_real_document_scope_excludes_other_document(self):
        other = Document.objects.create(title="unrelated.txt", file=SimpleUploadedFile("unrelated.txt", b"Saturn has rings. Jupiter is a gas giant."), file_type="txt", workspace_key="test:other")
        try:
            process_document(other)
            results = retrieve("Which planet has rings?", [self.doc.id])
            self.assertTrue(all(r["chunk"].document_id == self.doc.id for r in results))
        finally:
            delete_document_vectors(other.id)
            other.file.delete(save=False)

    def test_real_vector_cleanup(self):
        delete_document_vectors(self.doc.id)
        self.assertEqual(get_chroma_collection().get(where={"doc_id":self.doc.id})["ids"], [])

    def test_model_is_reused_and_longer_supported_token_limit_is_explicit(self):
        self.assertIs(get_embedder(), self.model)
        self.assertEqual(self.model.max_seq_length, 512)

    @skipUnless(os.getenv("DOCUMIND_LIVE_GEMINI") == "1", "Generation not enabled; pass --gemini for a real API request")
    def test_live_gemini_grounded_answer_and_unknown_question(self):
        results = retrieve("What is the project budget?", [self.doc.id])
        answer, sources, mode = generate_answer("What is the project budget?", results)
        self.assertEqual(mode, "gemini", answer)
        self.assertTrue(sources)
        self.assertIn("750", answer.replace(",", ""))
        self.assertIn("[Source", answer)
        unknown = "Who won the 2022 football world cup?"
        answer, sources, mode = generate_answer(unknown, retrieve(unknown, [self.doc.id]))
        self.assertEqual(mode, "no_evidence", answer)
        self.assertEqual(sources, [])

    @skipUnless(os.getenv("DOCUMIND_LIVE_GEMINI") == "1", "Pass --gemini to verify response-language matching")
    def test_live_gemini_matches_hinglish_hindi_and_marathi_response_requests(self):
        import re
        questions = [
            ("Hinglish", "Project ka budget kitna hai? Roman Hinglish me jawab do.", False),
            ("Hindi", "परियोजना का बजट कितना है? हिंदी में उत्तर दें।", True),
            ("Marathi", "प्रकल्पाचे अंदाजपत्रक किती आहे? मराठीत उत्तर द्या.", True),
        ]
        for language, question, devanagari in questions:
            with self.subTest(language=language):
                info = understand_query(question)
                answer, sources, mode = generate_answer(question, retrieve(question, [self.doc.id], query_info=info), info)
                self.assertEqual(mode, "gemini", answer)
                self.assertTrue(sources)
                self.assertIn("750", answer.replace(",", ""))
                self.assertEqual(bool(re.search(r"[\u0900-\u097f]", answer)), devanagari)
                print(f"  {language}: live generation returned grounded citations and the requested script")
