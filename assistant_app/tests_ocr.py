"""Fast OCR boundary tests; real engine checks are opt-in with DOCUMIND_OCR_TEST=1."""
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest import skipUnless
from unittest.mock import patch, Mock

from django.test import SimpleTestCase, override_settings
from pypdf import PdfReader, PdfWriter

from .services.extraction import extract_pages
from .services.ocr import recognize_pages
from .test_fixtures import pdf_bytes, scanned_pdf_bytes


class ExtractionOcrTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "scan.pdf"

    def test_native_text_and_blank_pages_never_start_ocr(self):
        self.path.write_bytes(pdf_bytes([None, "Native text is preserved."]))
        with patch("assistant_app.services.ocr.recognize_pages") as ocr:
            self.assertEqual(extract_pages(self.path, "pdf"), [(1, ""), (2, "Native text is preserved.\n")])
            ocr.assert_not_called()

    def test_mixed_pdf_keeps_physical_pages_and_does_not_duplicate_native_text(self):
        writer = PdfWriter()
        writer.append(PdfReader(BytesIO(pdf_bytes(["Native budget 100."]))))
        writer.append(PdfReader(BytesIO(scanned_pdf_bytes(["Scanned budget 750000."]))))
        writer.append(PdfReader(BytesIO(pdf_bytes([None]))))
        with self.path.open("wb") as stream:
            writer.write(stream)
        with patch("assistant_app.services.ocr.recognize_pages", return_value={2:"Scanned budget 750000."}) as ocr:
            pages = extract_pages(self.path, "pdf")
            self.assertEqual(pages, [(1,"Native budget 100.\n"),(2,"Scanned budget 750000."),(3,"")])
            ocr.assert_called_once_with(self.path, [2])

    def test_txt_is_not_sent_to_ocr(self):
        self.path.write_text("Plain text", encoding="utf-8")
        with patch("assistant_app.services.ocr.recognize_pages") as ocr:
            self.assertEqual(extract_pages(self.path, "txt"), [(1,"Plain text")])
            ocr.assert_not_called()

    @override_settings(OCR_ENABLED=False)
    def test_disabled_ocr_is_explicit(self):
        with self.assertRaisesMessage(ValueError, "Enable OCR_ENABLED"):
            recognize_pages(self.path, [1])

    @override_settings(OCR_MAX_PAGES=1)
    def test_limit_does_not_silently_truncate_pages(self):
        with self.assertRaisesMessage(ValueError, "Split it"):
            recognize_pages(self.path, [1,2])

    def test_missing_language_models_give_setup_instructions(self):
        with override_settings(OCR_TESSDATA_PATH=self.temp.name):
            with self.assertRaisesMessage(ValueError, "scripts/setup_ocr.py"):
                recognize_pages(self.path, [1])

    def mock_runtime(self):
        patches = [patch("assistant_app.services.ocr.importlib.util.find_spec", return_value=True),
                   patch("assistant_app.services.ocr.Path.is_file", return_value=True)]
        for item in patches:
            item.start(); self.addCleanup(item.stop)

    def test_timeout_is_bounded_and_actionable(self):
        self.mock_runtime()
        with patch("assistant_app.services.ocr.subprocess.run", side_effect=subprocess.TimeoutExpired("ocr", 1)):
            with self.assertRaisesMessage(ValueError, "OCR timed out"):
                recognize_pages(self.path, [2])

    def test_worker_failures_never_expose_private_stderr(self):
        self.mock_runtime()
        with patch("assistant_app.services.ocr.subprocess.run", return_value=Mock(returncode=1, stderr="PRIVATE TEXT")):
            with self.assertRaisesMessage(ValueError, "Local OCR failed") as result:
                recognize_pages(self.path, [2])
            self.assertNotIn("PRIVATE", str(result.exception))

    def test_worker_output_must_match_requested_physical_pages(self):
        self.mock_runtime()
        for response in [{"1":"wrong page"}, {"2":42}, []]:
            with patch("assistant_app.services.ocr.subprocess.run", return_value=Mock(returncode=0, stdout=json.dumps(response))):
                with self.assertRaisesMessage(ValueError, "invalid result"):
                    recognize_pages(self.path, [2])
        with patch("assistant_app.services.ocr.subprocess.run", return_value=Mock(returncode=0, stdout='{"2":" Actual scan text "}')):
            self.assertEqual(recognize_pages(self.path, [2]), {2:"Actual scan text"})


@skipUnless(os.getenv("DOCUMIND_OCR_TEST") == "1", "Set DOCUMIND_OCR_TEST=1 for real local OCR")
class RealOcrTests(SimpleTestCase):
    def test_real_image_only_english_and_hinglish(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scanned_facts.pdf"
            path.write_bytes(scanned_pdf_bytes(["Aurora Flood Project\nBudget is 750000 rupees.\nDeadline is 15 December 2026.", "Project ka budget 750000 hai.\nRelease code AURORA42 hai."]))
            self.assertTrue(all(not page.extract_text().strip() for page in PdfReader(path).pages))
            pages = extract_pages(path, "pdf")
            self.assertEqual([page for page, _ in pages], [1,2])
            self.assertIn("750000", pages[0][1]); self.assertIn("December 2026", pages[0][1])
            self.assertIn("750000", pages[1][1]); self.assertIn("AURORA42", pages[1][1])

    def test_real_hindi_and_marathi_scans(self):
        font = Path(os.getenv("DOCUMIND_TEST_DEVANAGARI_FONT", "C:/Windows/Fonts/Nirmala.ttc"))
        if not font.exists():
            self.skipTest("A Devanagari fixture font is not installed")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scanned_languages.pdf"
            path.write_bytes(scanned_pdf_bytes(["परियोजना का बजट 750000 रुपये है।", "प्रकल्पाचे बजेट 750000 रुपये आहे."], font_path=font))
            pages = extract_pages(path, "pdf")
            self.assertIn("750000", pages[0][1]); self.assertIn("बजट", pages[0][1])
            self.assertIn("750000", pages[1][1]); self.assertIn("आहे", pages[1][1])
