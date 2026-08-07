"""The command line: run claims, review them, look one up."""

import argparse
import sys

from . import store
from .agent import Context, load_policies, run_folder
from .models import Status

# a short label for each status, so the terminal output stays readable
LABELS = {
    Status.APPROVED: "APPROVED",
    Status.REJECTED: "REJECTED",
    Status.NEEDS_REVIEW: "NEEDS REVIEW",
    Status.FAILED: "COULD NOT READ",
    Status.HUMAN_APPROVED: "APPROVED BY HUMAN",
    Status.HUMAN_REJECTED: "REJECTED BY HUMAN",
}


def money(claim):
    """Show the claim amount, or a dash if we never found one."""
    return f"${claim.amount:,.2f}" if claim.amount is not None else "-"


def reason(state):
    """The single most useful sentence about this claim."""
    if state.error:
        return state.error
    if state.problems:
        return state.problems[0].message
    return "Every check passed."


def count(number, word):
    """Say '1 claim' but '3 claims'."""
    return f"{number} {word}" if number == 1 else f"{number} {word}s"


def shorten(text, width=58):
    """Cut a long sentence down so the table stays lined up."""
    return text if len(text) <= width else text[: width - 3] + "..."


def print_table(states):
    """Print one line per claim."""
    print(f"{'CLAIM':<14} {'STATUS':<18} {'AMOUNT':>12}  WHY")
    print("-" * 78)
    for state in states:
        label = LABELS.get(state.status, state.status.value)
        print(
            f"{shorten(state.claim.reference, 14):<14} {label:<18} "
            f"{money(state.claim):>12}  {shorten(reason(state))}"
        )


def command_run(args):
    """Run every claim document at the given path."""
    context = Context(policies=load_policies(args.policies) if args.policies else None)
    states = run_folder(args.path, context)
    if not states:
        print(f"No claim files found at '{args.path}'.")
        return 1

    for state in states:
        store.save(state, args.queue)
    print_table(states)

    waiting = [s for s in states if s.status == Status.NEEDS_REVIEW]
    print()
    print(f"{count(len(states), 'claim')} processed. {len(waiting)} waiting for a human.")
    if waiting:
        # tell the caseworker exactly what to do next
        print("Next step:  python -m claimflow review")
    return 0


def command_list(args):
    """Show everything saved in the queue."""
    states = store.load_all(args.queue)
    if not states:
        print(f"The queue at '{args.queue}' is empty.")
        return 0
    print_table(states)
    return 0


def command_show(args):
    """Print the full letter or summary for one claim."""
    state = store.load(args.reference, args.queue)
    print(state.letter)
    print("--- WHAT THE AGENT DID ---")
    for line in state.history:
        print(f"  {line}")
    return 0


def ask_text(prompt, on_no_answer=""):
    """Ask the caseworker something and return what they typed."""
    try:
        return input(prompt).strip()
    except EOFError:
        # no one is at the keyboard, so do not crash
        return on_no_answer


def ask(prompt):
    """Ask the caseworker a yes-or-no style question."""
    return ask_text(prompt, on_no_answer="quit").lower()


def command_review(args):
    """Walk the caseworker through every claim that is waiting."""
    pending = store.load_pending(args.queue)
    if not pending:
        print("Nothing is waiting for review. You are all caught up.")
        return 0

    print(f"{count(len(pending), 'claim')} waiting for you.\n")
    for number, state in enumerate(pending, start=1):
        print("=" * 78)
        print(f"[{number} of {len(pending)}]")
        print(state.letter)

        while True:
            answer = ask("approve / reject / skip / quit > ")
            if answer in ("approve", "a", "reject", "r"):
                decision = "approve" if answer in ("approve", "a") else "reject"
                note = ask_text("Reason (press Enter to skip): ")
                store.record_decision(
                    state.claim.reference, decision, args.reviewer, note, args.queue
                )
                done = "approved" if decision == "approve" else "rejected"
                print(f"Saved. {state.claim.reference} was {done} by {args.reviewer}.\n")
                break
            if answer in ("skip", "s", ""):
                print("Skipped. It stays in the queue.\n")
                break
            if answer in ("quit", "q"):
                print("Stopping. Everything you decided is saved.")
                return 0
            print("Please type approve, reject, skip or quit.")
    return 0


def build_parser():
    """Describe every command the tool accepts."""
    parser = argparse.ArgumentParser(
        prog="claimflow", description="Review insurance claims with a human in the loop."
    )
    parser.add_argument("--queue", default=store.DEFAULT_QUEUE, help="where claims are saved")
    commands = parser.add_subparsers(dest="command", required=True)

    runner = commands.add_parser("run", help="read claim files and decide on them")
    runner.add_argument("path", help="a claim file, or a folder of them")
    runner.add_argument("--policies", help="a different policy records file")
    runner.set_defaults(handler=command_run)

    lister = commands.add_parser("list", help="show every claim in the queue")
    lister.set_defaults(handler=command_list)

    shower = commands.add_parser("show", help="print one claim's letter in full")
    shower.add_argument("reference", help="a claim id, for example CLM-1002")
    shower.set_defaults(handler=command_show)

    reviewer = commands.add_parser("review", help="approve or reject the waiting claims")
    reviewer.add_argument("--reviewer", default="caseworker", help="your name, for the record")
    reviewer.set_defaults(handler=command_review)

    return parser


def main(argv=None):
    """Run the command the user typed."""
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except RuntimeError as problem:
        # expected problems get a plain message, not a stack trace
        print(f"Error: {problem}", file=sys.stderr)
        return 1
