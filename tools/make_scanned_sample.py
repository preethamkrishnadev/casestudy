"""Builds the scanned sample claim: a PDF with pictures in it and no text at all.

Run this once when you want to rebuild the sample. The PDF it writes is kept in
the repository, so nobody needs Pillow just to run the tests.

    pip install pillow
    python3 tools/make_scanned_sample.py
"""

import os
import random
import re

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "samples_pdf", "claim_2002_scanned.pdf")

# a letter-size page at 200 dots per inch, which is what an office scanner gives you
WIDTH, HEIGHT = 1700, 2200

CLAIM = """\
NORTHGATE COMMUNITY HOSPITAL
Claim submission - scanned copy


Claim Reference: CLM-2002

Policy Number: POL-445120

Claimant Name: David Okafor


Treatment provided
------------------

The member attended the outpatient clinic following a fall at home.
An X-ray of the left wrist was taken and a support splint was fitted.
No fracture was found. The member was discharged the same morning and
attended one follow-up appointment two weeks later.


Billing summary
---------------

Claim Amount: $3,150.00


Provider certification: the services listed were medically necessary.
"""

FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
]


def pick_font(size):
    """Find a real font on this machine, because the built-in one is too small to read."""
    for path in FONTS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    raise SystemExit("No TrueType font found. Install fonts-dejavu and try again.")


def add_scanner_noise(page, seed=20260807):
    """Make the page look like it came off a real scanner, not out of a printer."""
    random.seed(seed)
    pixels = page.load()
    # a light dusting of grey specks, the way a glass platen picks up dust
    for _ in range(WIDTH * HEIGHT // 900):
        x = random.randrange(WIDTH)
        y = random.randrange(HEIGHT)
        pixels[x, y] = random.randrange(150, 225)
    # a scan is never perfectly square on the glass
    return page.rotate(0.35, resample=Image.BICUBIC, fillcolor=255)


def freeze_dates(path):
    """Pin the timestamps Pillow writes, so rebuilding does not churn the repository."""
    with open(path, "rb") as handle:
        pdf = handle.read()
    # the replacement is the same length as a real date, so byte offsets still line up
    pdf = re.sub(rb"D:\d{14}Z", b"D:20260101000000Z", pdf)
    with open(path, "wb") as handle:
        handle.write(pdf)


def main():
    page = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(page)
    draw.multiline_text((150, 170), CLAIM, fill=30, font=pick_font(38), spacing=10)

    page = add_scanner_noise(page)
    # saving an image as a PDF gives us a page with a picture on it and no font
    page.save(OUT, "PDF", resolution=200.0)
    freeze_dates(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
