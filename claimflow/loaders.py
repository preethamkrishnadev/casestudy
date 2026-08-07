"""Turns a claim file on disk into plain text."""

import os

from . import ocr


class Reading:
    """How we got the text out of one file, so a human can see it later."""

    def __init__(self):
        # "text" means we copied it straight out, "ocr" means we read a picture
        self.text_source = "text"
        self.notes = []

    def used_ocr(self, pages):
        """Remember that this document had to be read by OCR."""
        self.text_source = "ocr"
        self.notes.append(f"The PDF had no text layer, so OCR read {pages} scanned page(s).")


def read_text(path, reading=None):
    """Read a normal .txt claim."""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def page_images(reader):
    """Every picture embedded in the document, page by page."""
    pictures = []
    for page in reader.pages:
        pictures.extend(image.data for image in page.images)
    return pictures


def read_pdf(path, reading=None):
    """Read a .pdf claim, if the optional pypdf library is installed."""
    try:
        import pypdf
    except ImportError:
        # a clear message beats a stack trace the client cannot act on
        raise RuntimeError(
            "This is a PDF, and reading PDFs needs an extra library. "
            "Run:  pip install pypdf"
        )
    reader = pypdf.PdfReader(path)
    # join every page into one block of text
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not ocr.looks_empty(text):
        return text

    # nothing to copy out, so this is a scan: read the pictures instead
    pictures = page_images(reader)
    if not pictures:
        raise RuntimeError("This PDF has no text in it and no pictures we could read.")
    text = ocr.read_images(pictures)
    if reading is not None:
        reading.used_ocr(len(pictures))
    return text


# add a new file type by adding one line here
LOADERS = {
    ".txt": read_text,
    ".text": read_text,
    ".pdf": read_pdf,
}


def supported(path):
    """True if we know how to read this file."""
    return os.path.splitext(path)[1].lower() in LOADERS


def load(path, reading=None):
    """Read any supported claim file and return its text."""
    extension = os.path.splitext(path)[1].lower()
    loader = LOADERS.get(extension)
    if loader is None:
        known = ", ".join(sorted(LOADERS))
        raise RuntimeError(f"Cannot read '{extension}' files. We handle: {known}")
    text = loader(path, reading)
    if not text.strip():
        # an empty document is a real problem, so say so plainly
        raise RuntimeError("The file opened but had no text in it.")
    return text
