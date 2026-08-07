"""Turns a claim file on disk into plain text."""

import os


def read_text(path):
    """Read a normal .txt claim."""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def read_pdf(path):
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
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# add a new file type by adding one line here
LOADERS = {
    ".txt": read_text,
    ".text": read_text,
    ".pdf": read_pdf,
}


def supported(path):
    """True if we know how to read this file."""
    return os.path.splitext(path)[1].lower() in LOADERS


def load(path):
    """Read any supported claim file and return its text."""
    extension = os.path.splitext(path)[1].lower()
    loader = LOADERS.get(extension)
    if loader is None:
        known = ", ".join(sorted(LOADERS))
        raise RuntimeError(f"Cannot read '{extension}' files. We handle: {known}")
    text = loader(path)
    if not text.strip():
        # an empty document is a real problem, so say so plainly
        raise RuntimeError("The file opened but had no text in it.")
    return text
