"""Reads the words off a scanned page, when there is no text layer to read."""

import io

# a page with fewer real characters than this never had a text layer worth having
MIN_TEXT = 30


def looks_empty(text):
    """True when a PDF gave us nothing a person could actually read."""
    # scans often hand back a stray form feed or a one-word watermark, not nothing
    return len("".join(text.split())) < MIN_TEXT


def read_images(images):
    """Read every page image with OCR and return one block of text."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        # a clear message beats a stack trace the client cannot act on
        raise RuntimeError(
            "This PDF has no text layer, so it has to be read by OCR. "
            "Run:  pip install claimflow[ocr]"
        )

    pages = []
    for data in images:
        picture = Image.open(io.BytesIO(data))
        try:
            pages.append(pytesseract.image_to_string(picture))
        except pytesseract.TesseractNotFoundError:
            # the Python package is installed but the program behind it is not
            raise RuntimeError(
                "This PDF needs OCR, and the Tesseract program itself is missing. "
                "Run:  sudo apt install tesseract-ocr"
            )
    return "\n".join(pages)
