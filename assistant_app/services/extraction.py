import re
import unicodedata


def extract_pages(path, file_type):
    """Physical PDF page numbers are 1-based. TXT uses a single logical section."""
    if file_type == "pdf":
        from pypdf import PdfReader
        try:
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ValueError("This PDF is password-protected. Upload an unlocked copy.")
            pages, scans = [], []
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                pages.append((i + 1, text))
                # Truly blank pages need no OCR. Short text plus an image may be
                # just a scan's page number/header; OCR the complete page once.
                resources = page.get("/Resources", {})
                if hasattr(resources, "get_object"):
                    resources = resources.get_object()
                has_images = bool(resources.get("/XObject"))
                if (not text.strip() and page.get_contents() is not None) or (has_images and len(text.strip()) < 80):
                    scans.append(i + 1)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("This PDF could not be read. Upload a valid, unlocked PDF.") from exc
        if scans:
            from .ocr import recognize_pages
            recognized = recognize_pages(path, scans)
            pages = [(number, recognized.get(number) or text) for number, text in pages]
        return pages
    if file_type != "txt":
        raise ValueError("Only PDF and TXT documents are supported.")
    try:
        with open(path, "r", encoding="utf-8-sig") as stream:
            text = stream.read()
    except UnicodeError as exc:
        raise ValueError("Save the TXT file with UTF-8 encoding and upload it again.") from exc
    if "\x00" in text:
        raise ValueError("This file contains binary data. Upload a UTF-8 TXT file.")
    return [(1, text)]


def split_text(text, chunk_size=900, overlap=160):
    if chunk_size < 80 or not 0 <= overlap < chunk_size // 2:
        raise ValueError("Chunk size must be at least 80; overlap must be less than half the size.")
    text = unicodedata.normalize("NFC", text).replace("\x00", "")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    chunks, seen, start = [], set(), 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            lower = start + int(chunk_size * 0.6)
            for separator in ("\n\n", ". ", "। ", "\n", " "):
                boundary = text.rfind(separator, lower, end)
                if boundary >= lower:
                    end = boundary + (1 if separator in (". ", "। ") else 0)
                    break
        piece = text[start:end].strip()
        if piece and piece not in seen:
            seen.add(piece)
            chunks.append(piece)
        if end == len(text):
            break
        next_start = max(start + 1, end - overlap)
        # Do not begin in the middle of a word.
        while next_start < end and not text[next_start - 1].isspace():
            next_start += 1
        start = next_start
    return chunks
