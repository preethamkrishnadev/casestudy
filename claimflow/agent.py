"""The agent: five small steps, run in order, with a safety net around each one."""

import json
import os

from . import letters, loaders
from .extract import DEFAULT_EXTRACTOR
from .models import ClaimState, Finding, Status
from .rules import BLOCK, RULES

# the pretend company records live next to this package
DEFAULT_POLICIES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "policies.json")


def load_policies(path=DEFAULT_POLICIES):
    """Read the company's policy records."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


class Context:
    """The tools a step is allowed to use."""

    def __init__(self, policies=None, extractor=None):
        self.policies = policies if policies is not None else load_policies()
        # swap this out for an LLM-backed extractor and nothing else changes
        self.extractor = extractor or DEFAULT_EXTRACTOR


def step_load(state, context):
    """Step 1: turn the file into text."""
    state.claim.raw_text = loaders.load(state.claim.source_file)
    state.log(f"Read {len(state.claim.raw_text)} characters from the document.")


def step_extract(state, context):
    """Step 2: find the name, amount and policy number."""
    state.claim = context.extractor.extract(state.claim.raw_text, state.claim.source_file)
    found = [
        name
        for name in ("claim_id", "claimant_name", "policy_number", "claim_amount")
        if not getattr(state.claim, name).is_missing
    ]
    state.log("Found: " + (", ".join(found) if found else "nothing"))


def step_validate(state, context):
    """Step 3: run every business rule."""
    for rule in RULES:
        passed, message = rule.check(state.claim, context.policies)
        state.findings.append(Finding(rule.name, passed, rule.severity, message))
    state.log(f"Ran {len(RULES)} rules, {len(state.problems)} failed.")


def step_decide(state, context):
    """Step 4: turn the failed rules into one decision."""
    blockers = [f for f in state.problems if f.severity == BLOCK]
    if blockers:
        state.status = Status.REJECTED
    elif state.problems:
        # something a rule could not settle, so a human must
        state.status = Status.NEEDS_REVIEW
    else:
        state.status = Status.APPROVED
    state.log(f"Decision: {state.status.value}")


def step_draft(state, context):
    """Step 5: write the letter or the exception summary."""
    state.letter = letters.draft(state)
    state.log("Drafted the document for a caseworker to sign.")


# the whole workflow, in the order it runs
STEPS = [step_load, step_extract, step_validate, step_decide, step_draft]


def run_one(path, context=None):
    """Run one claim document through the whole workflow."""
    context = context or Context()
    state = ClaimState()
    state.claim.source_file = path
    state.log(f"Started on {os.path.basename(path)}")

    for step in STEPS:
        try:
            step(state, context)
        except Exception as problem:
            # one bad document must never stop the batch
            state.status = Status.FAILED
            state.error = str(problem)
            state.log(f"Stopped at {step.__name__}: {problem}")
            state.letter = letters.draft(state)
            return state
    return state


def find_claims(path):
    """List the claim files at this path, whether it is a file or a folder."""
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        raise RuntimeError(f"There is nothing at '{path}'.")
    names = sorted(os.listdir(path))
    return [os.path.join(path, n) for n in names if loaders.supported(n)]


def run_folder(path, context=None):
    """Run every claim document at this path."""
    context = context or Context()
    return [run_one(claim, context) for claim in find_claims(path)]
