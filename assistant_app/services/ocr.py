"""Bounded, local OCR subprocess; no document content leaves this machine."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from django.conf import settings


def recognize_pages(path, page_numbers):
    if not settings.OCR_ENABLED:
        raise ValueError("This PDF needs OCR. Enable OCR_ENABLED and install the local OCR dependencies/models.")
    if len(page_numbers) > settings.OCR_MAX_PAGES:
        raise ValueError(f"This PDF needs OCR on {len(page_numbers)} pages; the limit is {settings.OCR_MAX_PAGES}. Split it into smaller PDFs.")
    languages = settings.OCR_LANGUAGES.split("+")
    if not languages or any(not re.fullmatch(r"[a-zA-Z0-9_]+", lang) for lang in languages):
        raise ValueError("OCR_LANGUAGES must contain Tesseract language codes, for example eng+hin+mar.")
    tessdata = Path(settings.OCR_TESSDATA_PATH)
    missing = [lang for lang in languages if not (tessdata / f"{lang}.traineddata").is_file()]
    if missing:
        raise ValueError(f"OCR language models missing: {', '.join(missing)}. Run python scripts/setup_ocr.py, then retry indexing.")
    if any(importlib.util.find_spec(name) is None for name in ("tesserocr", "pypdfium2", "PIL")):
        raise ValueError("Local OCR dependencies are missing. Install requirements.txt; see docs/OCR.md for Windows setup.")
    job = {"path": str(Path(path).resolve()), "pages": page_numbers, "languages": "+".join(languages),
           "tessdata": str(tessdata.resolve()), "dpi": min(300, max(100, settings.OCR_DPI))}
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("ocr_worker.py"))],
            input=json.dumps(job), capture_output=True, text=True, encoding="utf-8",
            timeout=max(1, settings.OCR_TIMEOUT_SECONDS), check=False,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("OCR timed out. Split this scan into smaller PDFs and retry indexing.") from exc
    except OSError as exc:
        raise ValueError("The local OCR worker could not start. Check the Python/OCR installation.") from exc
    if result.returncode:
        raise ValueError("Local OCR failed. Check the OCR installation/language models and try a clear, upright scan. See docs/OCR.md.")
    try:
        data = json.loads(result.stdout)
        if set(data) != {str(page) for page in page_numbers} or any(not isinstance(value, str) for value in data.values()):
            raise ValueError("Unexpected OCR result")
        return {int(page): text.strip() for page, text in data.items()}
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("OCR returned an invalid result. Retry indexing the document.") from exc
