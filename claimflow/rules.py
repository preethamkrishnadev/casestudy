"""The business rules a claim must pass."""

# a claim worth more than this always needs a human to sign off
AUTO_APPROVE_LIMIT = 10_000

# a BLOCK failure rejects the claim outright
BLOCK = "BLOCK"
# a REVIEW failure sends the claim to a human caseworker
REVIEW = "REVIEW"

# every rule registers itself here when the file loads
RULES = []


class Rule:
    """One business rule and how serious it is."""

    def __init__(self, name, severity, check):
        self.name = name
        self.severity = severity
        self.check = check


def rule(name, severity):
    """Register a function as a business rule."""

    def register(function):
        RULES.append(Rule(name, severity, function))
        return function

    return register


def policy_for(claim, policies):
    """Look up this claim's policy in the company records."""
    return policies.get(claim.policy_number.value)


def pretty(label, value):
    """Show a value the way a person would write it."""
    # amounts are stored as plain numbers, so add the dollar sign back
    if label == "claim amount":
        return f"${float(value):,.2f}"
    return value


@rule("required_fields_present", REVIEW)
def required_fields_present(claim, policies):
    """We need a name, an amount, and a policy number to judge a claim."""
    labels = {
        "claimant name": claim.claimant_name,
        "claim amount": claim.claim_amount,
        "policy number": claim.policy_number,
    }
    missing = [label for label, value in labels.items() if value.is_missing]
    if missing:
        return False, "The document is missing the " + " and the ".join(missing) + "."
    return True, "All the facts we need are in the document."


@rule("no_conflicting_values", REVIEW)
def no_conflicting_values(claim, policies):
    """The document must not say two different things about the same fact."""
    labels = {
        "claimant name": claim.claimant_name,
        "claim amount": claim.claim_amount,
        "policy number": claim.policy_number,
    }
    clashes = []
    for label, value in labels.items():
        if value.is_conflicting:
            shown = [pretty(label, v) for v in value.values]
            clashes.append(f"{label} appears as {' and '.join(shown)}")
    if clashes:
        return False, "The document contradicts itself: " + "; ".join(clashes) + "."
    return True, "The document is consistent with itself."


@rule("policy_on_file", BLOCK)
def policy_on_file(claim, policies):
    """The policy number must exist in our records."""
    if claim.policy_number.is_missing:
        # nothing to look up, and the missing-fields rule already caught this
        return True, "No policy number to look up."
    if policy_for(claim, policies) is None:
        return False, f"Policy {claim.policy_number.value} is not in our records."
    return True, f"Policy {claim.policy_number.value} was found in our records."


@rule("policy_is_active", BLOCK)
def policy_is_active(claim, policies):
    """The policy must still be active on the day we review it."""
    policy = policy_for(claim, policies)
    if policy is None:
        return True, "No policy to check."
    status = policy.get("status", "unknown")
    if status != "active":
        return False, f"Policy {claim.policy_number.value} is {status}, not active."
    return True, "The policy is active."


@rule("within_coverage_limit", BLOCK)
def within_coverage_limit(claim, policies):
    """The claim cannot ask for more than the policy covers."""
    policy = policy_for(claim, policies)
    if policy is None or claim.amount is None:
        return True, "Not enough information to check the coverage limit."
    limit = policy.get("coverage_limit", 0)
    if claim.amount > limit:
        return False, (
            f"The claim asks for ${claim.amount:,.2f} but the policy only covers "
            f"${limit:,.2f}."
        )
    return True, f"The amount fits inside the ${limit:,.2f} coverage limit."


@rule("under_auto_approve_limit", REVIEW)
def under_auto_approve_limit(claim, policies):
    """Big claims are never approved automatically."""
    if claim.amount is None:
        return True, "No amount to compare."
    if claim.amount > AUTO_APPROVE_LIMIT:
        return False, (
            f"The claim is for ${claim.amount:,.2f}, which is over the "
            f"${AUTO_APPROVE_LIMIT:,.0f} auto-approval limit."
        )
    return True, f"The amount is under the ${AUTO_APPROVE_LIMIT:,.0f} auto-approval limit."


@rule("name_matches_policy_holder", REVIEW)
def name_matches_policy_holder(claim, policies):
    """The person claiming must be the person on the policy."""
    policy = policy_for(claim, policies)
    if policy is None or claim.claimant_name.is_missing:
        return True, "Not enough information to check the name."
    holder = policy.get("holder", "")
    if claim.claimant_name.value.lower() != holder.lower():
        return False, (
            f"The claim is from {claim.claimant_name.value} but the policy belongs "
            f"to {holder}."
        )
    return True, "The name matches the policy holder."
