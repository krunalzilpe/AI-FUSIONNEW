"""Private worker: one PDF, one Tesseract instance, one rendered page at a time.

The parent kills this process on timeout. Never print page text to stderr.
"""
import json
import math
import sys


def recognize(job):
    import pypdfium2 as pdfium
    from tesserocr import PyTessBaseAPI, OEM, PSM

    result = {}
    with pdfium.PdfDocument(job["path"]) as pdf:
        with PyTessBaseAPI(path=job["tessdata"], lang=job["languages"], oem=OEM.LSTM_ONLY, psm=PSM.AUTO) as engine:
            for number in job["pages"]:
                page = pdf[number - 1]
                try:
                    width, height = page.get_size()
                    if width <= 0 or height <= 0:
                        raise ValueError("Invalid page size")
                    # Bound bitmap allocation even for unusual PDF page dimensions.
                    scale = min(job["dpi"] / 72, math.sqrt(12_000_000 / (width * height)))
                    bitmap = page.render(scale=scale, rev_byteorder=True)
                    try:
                        image = bitmap.to_pil()
                        try:
                            engine.SetImage(image)
                            result[str(number)] = engine.GetUTF8Text().strip()
                            engine.Clear()
                        finally:
                            image.close()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
    return result


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        print(json.dumps(recognize(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        # The parent exposes a controlled error; private document text is omitted.
        print(type(exc).__name__, file=sys.stderr)
        sys.exit(1)
