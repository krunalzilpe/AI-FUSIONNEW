"""Small deterministic PDF fixtures without an additional PDF-writing dependency."""
from io import BytesIO
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def pdf_bytes(text_pages):
    writer = PdfWriter()
    for text in text_pages:
        page = writer.add_blank_page(width=612, height=792)
        if text is None:
            continue
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        lines = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in text.splitlines()]
        stream.set_data(("BT /F1 11 Tf 40 740 Td 15 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET").encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


KNOWN_PAGES = [
    "Aurora Flood Monitoring Project\nThe main objective is to send early flood warnings to nearby villages.\nThe project detects rising river water levels.",
    "Project Administration\nThe project budget is 750000 Indian rupees.\nThe installation deadline is 15 December 2026.\nThe project coordinator is Anika Rao.",
    "Technical Design\nUltrasonic sensors measure river levels.\nSolar panels power the monitoring stations.\nAlerts are sent by SMS.\nMeasurements are recorded every ten minutes.",
]


def scanned_pdf_bytes(text_pages, font_path=None):
    """Image-only PDF fixture: there is deliberately no searchable text layer."""
    from PIL import Image, ImageDraw, ImageFont
    font = None
    for candidate in ([font_path] if font_path else ["arial.ttf", "DejaVuSans.ttf"]):
        try:
            font = ImageFont.truetype(str(candidate), 42)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(size=42)
    pages = []
    try:
        for text in text_pages:
            image = Image.new("RGB", (1200, 1600), "white")
            ImageDraw.Draw(image).multiline_text((80, 120), text, font=font, fill="black", spacing=24)
            pages.append(image)
        output = BytesIO()
        pages[0].save(output, format="PDF", resolution=150, save_all=True, append_images=pages[1:])
        return output.getvalue()
    finally:
        for image in pages:
            image.close()
