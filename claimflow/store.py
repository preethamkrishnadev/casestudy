"""Saves claims to disk so the agent can stop and a human can pick up later."""

import json
import os
import re
from datetime import datetime

from . import letters
from .models import ClaimState, Finding, Status
from .rules import REVIEW

# where the waiting claims live
DEFAULT_QUEUE = "queue"


def safe_name(reference):
    """Turn a claim reference into a safe file name."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(reference))


def path_for(reference, queue_dir=DEFAULT_QUEUE):
    """Where this claim is saved."""
    return os.path.join(queue_dir, safe_name(reference) + ".json")


def save(state, queue_dir=DEFAULT_QUEUE):
    """Write one claim to disk."""
    os.makedirs(queue_dir, exist_ok=True)
    target = path_for(state.claim.reference, queue_dir)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(state.to_dict(), handle, indent=2)
    return target


def load(reference, queue_dir=DEFAULT_QUEUE):
    """Read one saved claim back."""
    target = path_for(reference, queue_dir)
    if not os.path.exists(target):
        raise RuntimeError(f"No saved claim called '{reference}'.")
    with open(target, "r", encoding="utf-8") as handle:
        return ClaimState.from_dict(json.load(handle))


def load_all(queue_dir=DEFAULT_QUEUE):
    """Read every saved claim."""
    if not os.path.isdir(queue_dir):
        return []
    states = []
    for name in sorted(os.listdir(queue_dir)):
        if name.endswith(".json"):
            with open(os.path.join(queue_dir, name), "r", encoding="utf-8") as handle:
                states.append(ClaimState.from_dict(json.load(handle)))
    return states


def load_pending(queue_dir=DEFAULT_QUEUE):
    """Read only the claims still waiting for a human."""
    return [s for s in load_all(queue_dir) if s.status == Status.NEEDS_REVIEW]


def record_decision(reference, decision, reviewer, note="", queue_dir=DEFAULT_QUEUE):
    """Save a caseworker's approve or reject, and write the final letter."""
    if decision not in ("approve", "reject"):
        raise RuntimeError("A decision must be 'approve' or 'reject'.")

    state = load(reference, queue_dir)
    if state.status != Status.NEEDS_REVIEW:
        raise RuntimeError(f"Claim {reference} is already {state.status.value}.")

    approved = decision == "approve"
    state.status = Status.HUMAN_APPROVED if approved else Status.HUMAN_REJECTED
    # the caseworker's call becomes part of the record, just like a rule result
    state.findings.append(
        Finding(
            rule="caseworker_decision",
            passed=approved,
            severity=REVIEW,
            message=note or f"A caseworker chose to {decision} this claim.",
        )
    )
    stamp = datetime.now().isoformat(timespec="seconds")
    state.log(f"{stamp}: {reviewer} chose to {decision} this claim.")
    # now that a human has decided, replace the summary with a real letter
    state.letter = letters.draft(state)
    save(state, queue_dir)
    return state
