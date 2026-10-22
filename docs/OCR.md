# Local OCR for scanned PDFs

Scanned PDF pages now use local Tesseract OCR before the existing chunking, embedding and retrieval pipeline. No cloud OCR API or API key is required. The original PDF is unchanged; physical page numbers and original filenames are retained in citations.

## Setup

The tested Windows environment uses Python 3.12 x64. `requirements.txt` includes the bundled Tesseract Windows wheel linked by the [tesserocr project](https://github.com/sirfz/tesserocr), PDFium rendering and Pillow. Other Windows Python versions need a matching wheel from [the Windows wheel repository](https://github.com/simonflueckiger/tesserocr-windows_build/releases). On Linux, install the Tesseract/Leptonica development libraries required by tesserocr before installing Python dependencies.

```powershell
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.venv\Scripts\python.exe scripts/setup_ocr.py
```

Setup downloads the official `eng`, `hin`, and `mar` [Tesseract language models](https://github.com/tesseract-ocr/tessdata_fast) at a pinned revision into `.cache/tessdata`. This has already been completed in the current workspace. Downloads happen during setup only; uploaded documents are not sent to an OCR service.

Restart Django after installation. Upload a scanned PDF normally. A previously failed upload can use **Retry indexing**. For an existing ready mixed PDF that was indexed before this upgrade, run `manage.py reindex_documents --document ID` locally to recover previously omitted scanned pages; existing documents are not automatically reprocessed.

## Behavior and limits

- Embedded text is preferred. Pages without text, or image-containing pages with fewer than 80 embedded characters, use OCR. Truly blank pages are skipped without shifting page numbers.
- Supports mixed PDFs with separate native-text and scanned pages. Images embedded inside an otherwise text-rich page are not independently OCRed.
- One OCR process per PDF reuses one Tesseract instance and renders one page at a time. Default limits: 50 OCR pages, 180 seconds per PDF, 200 DPI and 12 million pixels per page. Timeout/failure is explicit rather than silently truncating the document.
- Defaults in `.env.example`: `OCR_ENABLED`, `OCR_LANGUAGES`, `OCR_TESSDATA_PATH`, `OCR_MAX_PAGES`, `OCR_TIMEOUT_SECONDS`, `OCR_DPI`. Missing language models/dependencies produce actionable errors.
- Intended for clear, upright printed scans. Handwriting, skew, blur, complex tables and unusual fonts are not guaranteed. OCR passages can contain recognition errors: verify the original PDF. Hindi/Marathi and Roman Hinglish were tested on small synthetic printed samples, not a broad accuracy benchmark.
- OCR output is stored as extracted source text in the existing index. No schema changes are required. Previously saved answers/citations retain their historical text.

## Verification commands

```powershell
$env:DOCUMIND_OCR_TEST='1'
.venv\Scripts\python.exe manage.py test assistant_app.tests assistant_app.tests_features assistant_app.tests_ocr
.venv\Scripts\python.exe -X utf8 test_rag_pipeline.py
# Against a separate running test server:
.venv\Scripts\python.exe scripts/smoke_http.py --url http://127.0.0.1:8002 --ocr
```

Real OCR checks cover image-only English/Hinglish, Hindi/Marathi sample facts and a scanned PDF through actual embeddings/Chroma retrieval with physical page-2 attribution. Fast tests cover mixed pages, blank/native/TXT bypass, missing models, limits, timeout, worker failures and page-result validation. Live Gemini generation is separate and was not retested for this OCR change.

Verified in this workspace: 57 regression/OCR tests passed; 8 real RAG integration tests passed (2 live Gemini tests skipped); the HTTP smoke including scanned-PDF upload/OCR/page-2 citation passed. Django checks and migration dry-run passed, and all 124 installed Python packages are compatible. The application server was restarted on port 8001 with OCR enabled.
