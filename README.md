# ClaimFlow

**An agent that reads insurance claim documents, decides what to do with them, and asks a
human whenever it is not sure.**

It reads a claim (text or PDF), pulls out the claimant's name, the claim amount and the policy
number, then checks those facts against a set of business rules. Easy claims it approves or
rejects on its own and writes the letter. Anything big or contradictory it **stops on**, and
writes an exception summary for a human caseworker to sign off.

Written in plain Python. **No libraries needed** to run it.

> This README covers what the system is and how it is built. For step-by-step operating
> procedures — daily run cycle, troubleshooting, backup and escalation — see
> **[RUNBOOK.md](RUNBOOK.md)**.

---

## Try it in 30 seconds

```bash
git clone <this-repo>
cd casestudy

python3 -m claimflow run samples/
```

You will see:

```
CLAIM          STATUS                   AMOUNT  WHY
------------------------------------------------------------------------------
CLM-1001       APPROVED              $4,200.00  Every check passed.
CLM-1002       NEEDS REVIEW         $18,500.00  The claim is for $18,500.00, which is over the $10,000 ...
CLM-1003       NEEDS REVIEW          $3,150.00  The document contradicts itself: claim amount appears a...
CLM-1004       REJECTED              $6,750.00  Policy POL-201558 is lapsed, not active.
CLM-1005       NEEDS REVIEW          $2,300.00  The document is missing the policy number.
claim_1006_... COULD NOT READ                -  The file opened but had no text in it.

6 claims processed. 3 waiting for a human.
Next step:  python -m claimflow review
```

Now put yourself in the caseworker's chair:

```bash
python3 -m claimflow review --reviewer "Your Name"
```

The agent shows you each stopped claim, explains why it stopped, and asks
`approve / reject / skip / quit`. Your answer is saved to disk, and the letter is rewritten as a
real approval or rejection.

---

## How it works

A claim walks through five small steps. Each step takes what we know so far and adds to it.

```
   [1] load  →  [2] extract  →  [3] validate  →  [4] decide  →  [5] draft
        |             |               |               |             |
      file         name,           7 business      APPROVED      letter or
      to text      amount,         rules           REJECTED      exception
                   policy no.                      NEEDS REVIEW  summary
                                                        |
                                                        ↓
                                              ┌──────────────────────┐
                                              │  HUMAN IN THE LOOP   │
                                              │  agent halts here    │
                                              │  caseworker decides  │
                                              └──────────────────────┘
```

If any step throws an error, the agent catches it, marks that one claim `COULD NOT READ`, writes
a short note explaining what went wrong, and **carries on with the next claim**. One bad file
never takes down the batch.

Every claim also carries an audit trail of exactly what the agent did:

```bash
python3 -m claimflow show CLM-1002
```

```
--- WHAT THE AGENT DID ---
  Started on claim_1002_high_value.txt
  Read 897 characters from the document.
  Found: claim_id, claimant_name, policy_number, claim_amount
  Ran 7 rules, 1 failed.
  Decision: NEEDS_REVIEW
  Drafted the document for a caseworker to sign.
  2026-08-07T09:59:11: P. Krishna chose to approve this claim.
```

---

## The business rules

A rule is either a **BLOCK** (reject the claim outright) or a **REVIEW** (stop and ask a human).

| Rule | Type | It fails when... |
|---|---|---|
| `required_fields_present` | REVIEW | the name, amount, or policy number is missing |
| `no_conflicting_values` | REVIEW | the document says two different things about the same fact |
| `policy_on_file` | BLOCK | the policy number is not in our records |
| `policy_is_active` | BLOCK | the policy has lapsed or been cancelled |
| `within_coverage_limit` | BLOCK | the claim asks for more than the policy covers |
| `under_auto_approve_limit` | REVIEW | the claim is over **$10,000** |
| `name_matches_policy_holder` | REVIEW | the claimant is not the person on the policy |

**How the decision is made**, in `claimflow/agent.py`:

1. Any BLOCK failed? → **REJECTED**
2. Otherwise, any REVIEW failed? → **NEEDS REVIEW** (the agent halts)
3. Otherwise → **APPROVED**

Rejecting always beats reviewing. If a policy has lapsed, there is nothing for a human to weigh
up.

---

## What each sample claim is here to prove

| File | What happens | Why it is in the repo |
|---|---|---|
| `claim_1001_clean.txt` | APPROVED | The happy path. Everything checks out, so no human is needed. |
| `claim_1002_high_value.txt` | NEEDS REVIEW | **$18,500 is over the $10,000 limit.** This is the main human-in-the-loop trigger. |
| `claim_1003_conflict.txt` | NEEDS REVIEW | The document says the amount is $3,150 in one place and $9,400 in another. **Conflicting data.** |
| `claim_1004_expired.txt` | REJECTED | The policy lapsed. A BLOCK rule, so the agent decides alone. |
| `claim_1005_missing.txt` | NEEDS REVIEW | The claimant lost their policy card, so a key fact is missing. |
| `claim_1006_unreadable.txt` | COULD NOT READ | A blank file, standing in for a bad scan. Proves one broken document does not stop the rest. |
| `samples_pdf/claim_2001_scanned.pdf` | REJECTED | A real PDF. Asks for $12,400 against a policy that only covers $8,000. |

---

## Reading PDFs

Text claims work out of the box. PDFs need one extra library:

```bash
pip install pypdf
python3 -m claimflow run samples_pdf/
```

Without it, the agent does not crash. It tells you exactly what to do:

```
CLM-2001   COULD NOT READ   -   This is a PDF, and reading PDFs needs an extra library. Run: pip install pypdf
```

---

## Built to be changed

Enterprise rules change every quarter. Three things were designed to be swapped without touching
the workflow.

### Add a business rule → write one function

Add this to `claimflow/rules.py` and you are done. Nothing else changes. The agent picks it up,
the letters explain it, and the caseworker sees it.

```python
@rule("claim_is_recent", BLOCK)
def claim_is_recent(claim, policies):
    """Claims must be filed within 90 days of treatment."""
    if claim.days_old is None:
        return True, "No date to check."
    if claim.days_old > 90:
        return False, f"The claim was filed {claim.days_old} days after treatment."
    return True, "The claim was filed on time."
```

### Change the money threshold → change one number

At the top of `claimflow/rules.py`:

```python
AUTO_APPROVE_LIMIT = 10_000
```

### Extract entities with an LLM instead → swap one object

The workflow never mentions regular expressions. It only asks for something with an `extract`
method, so a language model can take over without a single change to `agent.py`:

```python
class LlmExtractor:
    def extract(self, text, source_file=""):
        # call your model here, then fill in the same Claim object
        ...

states = run_folder("samples/", Context(extractor=LlmExtractor()))
```

**The default is deliberately not an LLM.** For a regulated claims process, rules that give the
same answer every time are easier to audit, cost nothing per claim, work with no network, and
cannot invent a policy number that was never on the page. The LLM slot is there for the messy
documents that rules genuinely cannot handle.

### Read a new file type → add one line

In `claimflow/loaders.py`:

```python
LOADERS = {".txt": read_text, ".pdf": read_pdf, ".docx": read_docx}
```

---

## How conflicting data is detected

This is the part worth a close look. The extractor does **not** stop at the first match. For each
field it collects *every* value it finds in the document:

```python
claim.claim_amount.values     # ["3150.00", "9400.00"]
claim.claim_amount.value      # "3150.00"  - the first one
claim.claim_amount.is_conflicting   # True
```

So conflict detection is one line in `claimflow/models.py`:

```python
return len(set(self.values)) > 1
```

If the same amount is written twice, it is one value and there is no conflict. If two different
amounts appear, the agent refuses to guess which one is right and hands it to a human. No
separate conflict engine was needed.

Patterns are anchored to field labels (`Claim Amount:`, `Total Billed:`) rather than to any
dollar sign in the text, so an itemised bill does not create false conflicts.

---

## Where the state lives

Every claim is saved as a JSON file under `queue/`:

```
queue/
├── CLM-1001.json     status: APPROVED
├── CLM-1002.json     status: NEEDS_REVIEW  ← waiting for a human
└── ...
```

This is what makes the halt real. The agent can finish and exit, the machine can reboot, and the
waiting claims are still there tomorrow morning. `python -m claimflow review` just reads that
folder.

The same claim cannot be decided twice. A second attempt is refused, so two caseworkers cannot
quietly overwrite each other.

---

## Commands

| Command | What it does |
|---|---|
| `python3 -m claimflow run samples/` | Read every claim at a path and decide on them |
| `python3 -m claimflow list` | Show everything in the queue and its current status |
| `python3 -m claimflow show CLM-1002` | Print one claim's full letter and audit trail |
| `python3 -m claimflow review` | Walk through the waiting claims and approve or reject them |

Useful flags: `--queue <folder>` to keep queues apart, `--policies <file>` to point at different
records, `--reviewer "Your Name"` to sign your decisions.

---

## Tests

```bash
python3 -m unittest discover tests -v
```

20 tests, standard library only. They cover every decision path, the error handling, the
persistence, and the double-decision guard.

---

## Project layout

```
casestudy/
├── claimflow/
│   ├── models.py     the data shapes, and the conflict check
│   ├── loaders.py    file on disk → text
│   ├── extract.py    text → name, amount, policy number
│   ├── rules.py      the 7 business rules
│   ├── agent.py      the 5 steps, run in order, errors caught
│   ├── letters.py    approval / rejection / exception templates
│   ├── store.py      the JSON queue: save, load, record a decision
│   └── cli.py        the run / list / show / review commands
├── samples/          six claim documents, one per outcome
├── samples_pdf/      the same idea, as a PDF
├── policies.json     stands in for the company's policy database
└── tests/
```

About 930 lines of Python, plus 190 lines of tests. Each file fits on one screen.

---

## Suggested 3-minute demo

A running order for the video walkthrough. Reset first with `rm -rf queue`.

**0:00 - The problem (20s).** Claims arrive as unstructured documents. A caseworker reads each
one by hand, checks it against policy records, and types a letter. Most claims are routine. The
expensive part is finding the few that are not.

**0:20 - One command (40s).** Run `python3 -m claimflow run samples/`. Six documents, six
outcomes, in under a second. Walk the table: one approved outright, one rejected outright, three
stopped for a human, one document that could not even be read — and note that the bad file did
not stop the other five.

**1:00 - Why it stopped (45s).** Run `python3 -m claimflow show CLM-1002`. Show the exception
summary: the claim, the amount, the one rule that tripped, and the six checks that passed.
Point out that this is written for a caseworker, not a developer. Then show the audit trail at
the bottom — every step the agent took, on the record.

**1:45 - The human decides (45s).** Run `python3 -m claimflow review`. Approve one, reject
another with a reason. Then run `list` in a **fresh** command to show the decisions survived the
process exiting — this is a durable queue, not an in-memory pause. Show that the rejected claim's
exception summary has been replaced by a real rejection letter carrying the caseworker's reason.

**2:30 - Why it will still work next quarter (30s).** Open `rules.py`. Change
`AUTO_APPROVE_LIMIT` from `10_000` to `4_000` and re-run: `CLM-1001` flips from APPROVED to
NEEDS REVIEW, and every letter now quotes the new figure. One number, no code change. Then show
that a new rule is one decorated function, and that the extractor is a swappable interface if
these documents ever get messy enough to need a model behind it.

---

## Notes for a technical reviewer

**Why hand-rolled orchestration and not LangChain?** The workflow is a list of five functions
with a `try` around each one. A framework would have added a dependency, a version to keep up
with, and a layer of indirection between a caseworker's question and the answer. The whole
orchestrator is 111 lines and there is nowhere for a bug to hide. The plug-in points that
actually matter — the extractor, the rules, the loaders — are exposed directly.

**Halting is a state, not an exception.** `NEEDS_REVIEW` is a normal outcome that gets written to
disk with a letter attached, not an error thrown up the stack. That is what lets the process end
cleanly and a person pick it up hours later.

**Every path produces something a human can read.** Approved, rejected, needs review, or the file
would not even open — in all four cases a caseworker gets a document explaining what happened and
what to do next. There is no outcome where a claim silently disappears.

**Rule messages are written for the claimant, not the developer.** Each rule returns its own
plain-English sentence, and that exact sentence flows into the letter. There is no second place
where error text has to be kept in sync.
