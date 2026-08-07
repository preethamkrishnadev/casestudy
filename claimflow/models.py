"""The data shapes ClaimFlow passes between steps."""

import os
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    """Where a claim is in its life."""

    NEW = "NEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_REJECTED = "HUMAN_REJECTED"


@dataclass
class Field:
    """One piece of information we pulled out of the claim."""

    # we keep every value we found, not just the first one
    values: list = field(default_factory=list)

    @property
    def value(self):
        """The value we will actually use."""
        # nothing found means nothing to use
        return self.values[0] if self.values else None

    @property
    def is_missing(self):
        """True when the document never mentioned this."""
        return not self.values

    @property
    def is_conflicting(self):
        """True when the document said two different things."""
        # this one line is our whole conflict detector
        return len(set(self.values)) > 1


@dataclass
class Claim:
    """The facts we extracted from one claim document."""

    claim_id: Field = field(default_factory=Field)
    claimant_name: Field = field(default_factory=Field)
    policy_number: Field = field(default_factory=Field)
    claim_amount: Field = field(default_factory=Field)
    source_file: str = ""
    raw_text: str = ""

    @property
    def amount(self):
        """The claim amount as a number, or None if we never found one."""
        if self.claim_amount.is_missing:
            return None
        return float(self.claim_amount.value)

    @property
    def reference(self):
        """A short name for this claim, used in logs and file names."""
        # fall back to the file name so every claim is addressable
        return self.claim_id.value or os.path.basename(self.source_file) or "UNKNOWN"


@dataclass
class Finding:
    """The result of running one business rule."""

    rule: str
    passed: bool
    severity: str
    # plain English, because this text goes straight to the caseworker
    message: str


@dataclass
class ClaimState:
    """Everything we know about one claim as it moves through the agent."""

    claim: Claim = field(default_factory=Claim)
    findings: list = field(default_factory=list)
    status: Status = Status.NEW
    letter: str = ""
    error: str = ""
    # an audit trail so a human can see exactly what the agent did
    history: list = field(default_factory=list)

    def log(self, message):
        """Add one line to the audit trail."""
        self.history.append(message)

    @property
    def problems(self):
        """Only the rules that failed."""
        return [f for f in self.findings if not f.passed]

    def to_dict(self):
        """Turn this state into plain data we can save as JSON."""
        return {
            "claim": {
                "claim_id": self.claim.claim_id.values,
                "claimant_name": self.claim.claimant_name.values,
                "policy_number": self.claim.policy_number.values,
                "claim_amount": self.claim.claim_amount.values,
                "source_file": self.claim.source_file,
                "raw_text": self.claim.raw_text,
            },
            "findings": [vars(f) for f in self.findings],
            "status": self.status.value,
            "letter": self.letter,
            "error": self.error,
            "history": self.history,
        }

    @staticmethod
    def from_dict(data):
        """Rebuild a state that was saved earlier."""
        raw = data["claim"]
        claim = Claim(
            claim_id=Field(raw["claim_id"]),
            claimant_name=Field(raw["claimant_name"]),
            policy_number=Field(raw["policy_number"]),
            claim_amount=Field(raw["claim_amount"]),
            source_file=raw["source_file"],
            raw_text=raw["raw_text"],
        )
        return ClaimState(
            claim=claim,
            findings=[Finding(**f) for f in data["findings"]],
            status=Status(data["status"]),
            letter=data["letter"],
            error=data["error"],
            history=data["history"],
        )
