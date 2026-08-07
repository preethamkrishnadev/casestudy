"""Tests: one for each thing the agent is supposed to do."""

import os
import shutil
import sys
import tempfile
import unittest

# let the tests import claimflow from the folder above
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claimflow import Status, run_folder, run_one
from claimflow import ocr, store
from claimflow.extract import RegexExtractor
from claimflow.rules import RULES

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), "samples")


def sample(name):
    """The full path to one sample claim."""
    return os.path.join(SAMPLES, name)


class TestExtraction(unittest.TestCase):
    """Does the extractor find the right facts?"""

    def test_finds_all_three_entities(self):
        claim = RegexExtractor().extract(
            "Policy Number: POL-889231\nClaimant Name: Maria Gonzalez\nClaim Amount: $4,200.00"
        )
        self.assertEqual(claim.claimant_name.value, "Maria Gonzalez")
        self.assertEqual(claim.policy_number.value, "POL-889231")
        self.assertEqual(claim.amount, 4200.0)

    def test_same_value_twice_is_not_a_conflict(self):
        claim = RegexExtractor().extract("Claim Amount: $500\nTotal Billed: 500.00")
        self.assertFalse(claim.claim_amount.is_conflicting)

    def test_two_different_values_is_a_conflict(self):
        claim = RegexExtractor().extract("Claim Amount: $500\nTotal Billed: $900")
        self.assertTrue(claim.claim_amount.is_conflicting)

    def test_missing_field_is_reported_as_missing(self):
        claim = RegexExtractor().extract("Claimant Name: Chen Wei")
        self.assertTrue(claim.policy_number.is_missing)
        self.assertIsNone(claim.amount)


class TestDecisions(unittest.TestCase):
    """Does each sample claim get the decision we expect?"""

    def test_clean_claim_is_approved(self):
        state = run_one(sample("claim_1001_clean.txt"))
        self.assertEqual(state.status, Status.APPROVED)
        self.assertEqual(state.problems, [])

    def test_big_claim_stops_for_a_human(self):
        state = run_one(sample("claim_1002_high_value.txt"))
        self.assertEqual(state.status, Status.NEEDS_REVIEW)
        self.assertIn("under_auto_approve_limit", [f.rule for f in state.problems])

    def test_contradicting_claim_stops_for_a_human(self):
        state = run_one(sample("claim_1003_conflict.txt"))
        self.assertEqual(state.status, Status.NEEDS_REVIEW)
        self.assertIn("no_conflicting_values", [f.rule for f in state.problems])

    def test_lapsed_policy_is_rejected(self):
        state = run_one(sample("claim_1004_expired.txt"))
        self.assertEqual(state.status, Status.REJECTED)
        self.assertIn("policy_is_active", [f.rule for f in state.problems])

    def test_missing_policy_number_stops_for_a_human(self):
        state = run_one(sample("claim_1005_missing.txt"))
        self.assertEqual(state.status, Status.NEEDS_REVIEW)
        self.assertIn("required_fields_present", [f.rule for f in state.problems])


class TestErrorHandling(unittest.TestCase):
    """Does one bad document leave the rest alone?"""

    def test_empty_document_fails_without_crashing(self):
        state = run_one(sample("claim_1006_unreadable.txt"))
        self.assertEqual(state.status, Status.FAILED)
        self.assertTrue(state.error)
        # a human still gets something readable to act on
        self.assertIn("COULD NOT PROCESS", state.letter)

    def test_missing_file_fails_without_crashing(self):
        state = run_one(sample("this_file_does_not_exist.txt"))
        self.assertEqual(state.status, Status.FAILED)

    def test_one_bad_file_does_not_stop_the_batch(self):
        states = run_folder(SAMPLES)
        self.assertEqual(len(states), 6)
        self.assertEqual(sum(1 for s in states if s.status == Status.FAILED), 1)
        self.assertEqual(sum(1 for s in states if s.status == Status.APPROVED), 1)


class TestPdfClaims(unittest.TestCase):
    """PDFs work the same way, if the optional library is installed."""

    PDF = os.path.join(os.path.dirname(HERE), "samples_pdf", "claim_2001_scanned.pdf")

    def test_pdf_claim_is_read_and_judged(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("pypdf is not installed; run: pip install pypdf")

        state = run_one(self.PDF)
        self.assertEqual(state.claim.claim_id.value, "CLM-2001")
        self.assertEqual(state.claim.amount, 12400.0)
        # the claim asks for more than this policy covers, so it is blocked
        self.assertEqual(state.status, Status.REJECTED)
        self.assertIn("within_coverage_limit", [f.rule for f in state.problems])

    def test_pdf_without_the_library_gives_a_clear_message(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            state = run_one(self.PDF)
            self.assertEqual(state.status, Status.FAILED)
            self.assertIn("pip install pypdf", state.error)
            return
        self.skipTest("pypdf is installed, so there is no missing-library message to check")


def ocr_is_available():
    """True when both the OCR libraries and the Tesseract program are installed."""
    try:
        import pypdf  # noqa: F401
        import pytesseract
        from PIL import Image  # noqa: F401

        pytesseract.get_tesseract_version()
    except Exception:
        # any failure here means we cannot run OCR, whatever the reason
        return False
    return True


class TestBlankPageDetection(unittest.TestCase):
    """Do we know a page with no text on it when we see one?"""

    def test_nothing_at_all_looks_empty(self):
        self.assertTrue(ocr.looks_empty(""))

    def test_a_stray_form_feed_looks_empty(self):
        # a scanned PDF often hands back this much and no more
        self.assertTrue(ocr.looks_empty("\x0c \n\x0c"))

    def test_a_real_page_does_not_look_empty(self):
        self.assertFalse(ocr.looks_empty("Claim Reference: CLM-2002\nClaim Amount: $3,150.00"))


class TestOcrFallback(unittest.TestCase):
    """Can we read a claim that arrived as a picture instead of as text?"""

    SCAN = os.path.join(os.path.dirname(HERE), "samples_pdf", "claim_2002_scanned.pdf")
    TEXT_PDF = os.path.join(os.path.dirname(HERE), "samples_pdf", "claim_2001_scanned.pdf")

    def setUp(self):
        if not ocr_is_available():
            self.skipTest("OCR is not set up; run: pip install claimflow[ocr]")

    def test_scanned_pdf_is_read_by_ocr(self):
        state = run_one(self.SCAN)
        self.assertEqual(state.claim.claim_id.value, "CLM-2002")
        self.assertEqual(state.claim.policy_number.value, "POL-445120")
        self.assertEqual(state.claim.amount, 3150.0)
        self.assertEqual(state.claim.text_source, "ocr")

    def test_ocr_claim_always_stops_for_a_human(self):
        state = run_one(self.SCAN)
        # nothing else is wrong with this claim, so OCR is the only reason it stopped
        self.assertEqual(state.status, Status.NEEDS_REVIEW)
        self.assertEqual(["text_is_machine_readable"], [f.rule for f in state.problems])

    def test_the_audit_trail_says_ocr_was_used(self):
        state = run_one(self.SCAN)
        self.assertIn("OCR", " ".join(state.history))

    def test_a_pdf_with_real_text_does_not_use_ocr(self):
        # OCR is the fallback, never the first thing we reach for
        state = run_one(self.TEXT_PDF)
        self.assertEqual(state.claim.text_source, "text")
        self.assertNotIn("text_is_machine_readable", [f.rule for f in state.problems])


class TestOcrIsOptional(unittest.TestCase):
    """Does a missing OCR setup explain itself instead of crashing?"""

    SCAN = os.path.join(os.path.dirname(HERE), "samples_pdf", "claim_2002_scanned.pdf")

    def test_missing_ocr_gives_a_clear_message(self):
        if ocr_is_available():
            self.skipTest("OCR is set up, so there is no missing-OCR message to check")
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("pypdf is not installed, so we never reach the OCR step")

        state = run_one(self.SCAN)
        self.assertEqual(state.status, Status.FAILED)
        # the caseworker must be told exactly what to install
        self.assertIn("install", state.error)
        self.assertIn("COULD NOT PROCESS", state.letter)


class TestEveryClaimGetsALetter(unittest.TestCase):
    """No claim may leave the agent without something a human can read."""

    def test_all_samples_have_a_letter_and_an_audit_trail(self):
        for state in run_folder(SAMPLES):
            self.assertTrue(state.letter.strip(), state.claim.reference)
            self.assertTrue(state.history, state.claim.reference)


class TestHumanSignOff(unittest.TestCase):
    """Does the queue survive the agent stopping?"""

    def setUp(self):
        self.queue = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.queue)

    def test_pending_claims_are_saved_and_reloaded(self):
        for state in run_folder(SAMPLES):
            store.save(state, self.queue)
        # three samples need a human: the big one, the contradicting one, the incomplete one
        self.assertEqual(len(store.load_pending(self.queue)), 3)

    def test_approving_updates_the_record_and_the_letter(self):
        store.save(run_one(sample("claim_1002_high_value.txt")), self.queue)
        store.record_decision("CLM-1002", "approve", "tester", "Checked by hand.", self.queue)

        reloaded = store.load("CLM-1002", self.queue)
        self.assertEqual(reloaded.status, Status.HUMAN_APPROVED)
        self.assertIn("approved", reloaded.letter)
        self.assertIn("Checked by hand.", reloaded.letter)
        self.assertEqual(store.load_pending(self.queue), [])

    def test_rejecting_records_the_reason(self):
        store.save(run_one(sample("claim_1003_conflict.txt")), self.queue)
        store.record_decision("CLM-1003", "reject", "tester", "Figures do not match.", self.queue)

        reloaded = store.load("CLM-1003", self.queue)
        self.assertEqual(reloaded.status, Status.HUMAN_REJECTED)
        self.assertIn("Figures do not match.", reloaded.letter)
        self.assertIn("tester", " ".join(reloaded.history))

    def test_the_same_claim_cannot_be_decided_twice(self):
        store.save(run_one(sample("claim_1002_high_value.txt")), self.queue)
        store.record_decision("CLM-1002", "approve", "tester", queue_dir=self.queue)
        with self.assertRaises(RuntimeError):
            store.record_decision("CLM-1002", "reject", "someone_else", queue_dir=self.queue)


class TestRulesAreExtensible(unittest.TestCase):
    """Adding a rule should need no changes anywhere else."""

    def test_every_rule_has_a_name_and_a_severity(self):
        self.assertEqual(len(RULES), 8)
        for rule in RULES:
            self.assertTrue(rule.name)
            self.assertIn(rule.severity, ("BLOCK", "REVIEW"))


if __name__ == "__main__":
    unittest.main()
