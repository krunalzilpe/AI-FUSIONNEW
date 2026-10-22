"""Download official pinned Tesseract models, never document data.

Run after installing requirements.txt: python scripts/setup_ocr.py
"""
import os
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "documind.settings")
from django.conf import settings

REVISION = "87416418657359cb625c412a48b6e1d6d41c29bd"


def main():
    directory = Path(settings.OCR_TESSDATA_PATH)
    directory.mkdir(parents=True, exist_ok=True)
    for language in settings.OCR_LANGUAGES.split("+"):
        if not re.fullmatch(r"[a-zA-Z0-9_]+", language):
            raise ValueError("Invalid OCR_LANGUAGES setting")
        target = directory / f"{language}.traineddata"
        if target.exists():
            print(f"Already installed: {language}")
            continue
        url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{REVISION}/{language}.traineddata"
        temporary = target.with_suffix(".download")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            if temporary.stat().st_size < 1000:
                raise ValueError("Invalid language model download")
            temporary.replace(target)
            print(f"Installed: {language}")
        finally:
            temporary.unlink(missing_ok=True)
    from tesserocr import PyTessBaseAPI
    with PyTessBaseAPI(path=str(directory), lang=settings.OCR_LANGUAGES):
        print("Local OCR engine and configured language models are ready.")


if __name__ == "__main__":
    main()
