"""Writes the letter or summary a human will read."""

from datetime import date

from .models import Status

APPROVAL = """\
{today}

Re: Claim {reference} - Policy {policy}

Dear {name},

We have finished reviewing your claim for {amount}. We are pleased to tell you
that it has been approved.

Our checks confirmed:
{checks}

Payment will follow under the usual terms of your policy.

Sincerely,
Claims Department

--- FOR CASEWORKER SIGN-OFF ---
Prepared automatically by ClaimFlow. Please review and sign.
"""

REJECTION = """\
{today}

Re: Claim {reference} - Policy {policy}

Dear {name},

We have finished reviewing your claim for {amount}. We are sorry to tell you
that we cannot approve it at this time.

The reason is:
{problems}

If you believe this is a mistake, you may reply to this letter with any extra
documents and we will look again.

Sincerely,
Claims Department

--- FOR CASEWORKER SIGN-OFF ---
Prepared automatically by ClaimFlow. Please review and sign.
"""

EXCEPTION = """\
=== EXCEPTION REVIEW - A HUMAN MUST DECIDE ===

Claim:      {reference}
Claimant:   {name}
Policy:     {policy}
Amount:     {amount}
Document:   {source}
Raised on:  {today}

WHY THE AGENT STOPPED
{problems}

WHAT THE AGENT DID CHECK
{checks}

WHAT WE NEED FROM YOU
Approve or reject this claim. The agent has gone as far as its rules allow and
will not decide this one on its own.

Run:  python -m claimflow review
"""

FAILURE = """\
=== COULD NOT PROCESS - {reference} ===

Document:   {source}
Raised on:  {today}

WHAT WENT WRONG
{error}

WHAT WE NEED FROM YOU
This document could not be read or understood. Please check the file and send
it again, or process this claim by hand.
"""


def bullets(items):
    """Turn a list of sentences into a bulleted block."""
    if not items:
        return "  (nothing to show)"
    return "\n".join(f"  - {item}" for item in items)


def facts(state):
    """The common details every letter starts with."""
    claim = state.claim
    return {
        "today": date.today().isoformat(),
        "reference": claim.reference,
        "name": claim.claimant_name.value or "Claimant",
        "policy": claim.policy_number.value or "not found",
        "amount": f"${claim.amount:,.2f}" if claim.amount is not None else "an unstated amount",
        "source": claim.source_file or "unknown file",
    }


def draft(state):
    """Pick the right template for this claim and fill it in."""
    details = facts(state)
    details["problems"] = bullets([f.message for f in state.problems])
    details["checks"] = bullets([f.message for f in state.findings if f.passed])
    details["error"] = state.error or "Unknown error."

    if state.status == Status.FAILED:
        return FAILURE.format(**details)
    if state.status in (Status.APPROVED, Status.HUMAN_APPROVED):
        return APPROVAL.format(**details)
    if state.status in (Status.REJECTED, Status.HUMAN_REJECTED):
        return REJECTION.format(**details)
    # anything left needs a person to look at it
    return EXCEPTION.format(**details)
