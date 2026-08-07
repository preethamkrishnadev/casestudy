"""Pulls the key facts out of messy claim text."""

import re

from .models import Claim, Field

# each field lists the patterns that can find it, so adding a field is a one-line change
PATTERNS = {
    "claim_id": [
        r"claim\s*(?:id|number|no\.?|reference|ref)\s*[:\-#]\s*(CLM-\d{3,10})",
        r"\b(CLM-\d{3,10})\b",
    ],
    "claimant_name": [
        r"(?:claimant|patient|member|insured)\s*(?:name)?\s*[:\-]\s*([A-Za-z][A-Za-z .'\-]{2,60})",
    ],
    "policy_number": [
        r"policy\s*(?:number|no\.?|#)?\s*[:\-]\s*([A-Z]{2,4}-?\d{4,10})",
        r"\b(POL-\d{4,10})\b",
    ],
    "claim_amount": [
        r"(?:claim\s*amount|amount\s*claimed|amount\s*requested|amount\s*billed"
        r"|total\s*billed|total\s*charges|billed\s*amount|total\s*claimed)"
        r"\s*[:\-]?\s*(?:USD|usd|\$)?\s*([\d,]+(?:\.\d{1,2})?)",
    ],
}


def clean_name(text):
    """Tidy up a person's name."""
    return " ".join(text.split()).strip(" .-'").title()


def clean_amount(text):
    """Turn '18,500.00' into the number 18500.0, written as text."""
    return f"{float(text.replace(',', '')):.2f}"


def clean_code(text):
    """Codes are always upper case with no spaces."""
    return text.replace(" ", "").upper()


# how to tidy each field once we have found it
CLEANERS = {
    "claim_id": clean_code,
    "claimant_name": clean_name,
    "policy_number": clean_code,
    "claim_amount": clean_amount,
}


def find_all(text, patterns, cleaner):
    """Find every match for one field and keep the distinct ones, in order."""
    found = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                value = cleaner(match.group(1))
            except (ValueError, AttributeError):
                # a match we cannot tidy is not a match we can trust
                continue
            # keep the reading order so the first mention wins
            if value and value not in found:
                found.append(value)
    return found


class RegexExtractor:
    """Finds claim facts using patterns. No network, no API key, same answer every time."""

    def extract(self, text, source_file=""):
        """Read the text and return a filled-in Claim."""
        claim = Claim(source_file=source_file, raw_text=text)
        for name, patterns in PATTERNS.items():
            values = find_all(text, patterns, CLEANERS[name])
            setattr(claim, name, Field(values))
        return claim


# swap this for any object with the same .extract(text, source_file) method
DEFAULT_EXTRACTOR = RegexExtractor()
