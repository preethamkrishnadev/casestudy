# ClaimFlow — Execution Runbook

This is the **operations** document. It tells you how to run ClaimFlow, day after day, and what
to do when something goes wrong.

It has two parts. **Part A** is for anyone reviewing this build who wants to verify it works —
about five minutes. **Part B** is for the team who will actually operate it.

For *why* the system is designed the way it is, read [README.md](README.md) instead. This
document does not explain design. It gives you steps to follow.

> **The one rule that matters most:** never run `run` twice over the same document. It erases
> caseworker decisions. See [B3](#b3-the-daily-cycle). This is not a bug you can work around by
> being careful — it is why the daily cycle moves documents to an archive folder.

---

# PART A — Verify this build

For a reviewer. Every command below was executed while writing this document, and the output
shown is what it actually printed.

## A1. Reproduction checklist

Start from a clean state:

```bash
cd casestudy
rm -rf queue
```

### Step 1 — Run the agent over the sample claims

```bash
python3 -m claimflow run samples/
```

Expect six rows and three claims held back for a human:

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

**What this proves:** the agent approves and rejects on its own where the rules are clear, halts
where they are not, and the one unreadable document did not stop the other five.

### Step 2 — Look at why a claim was held back

```bash
python3 -m claimflow show CLM-1002
```

Expect the exception summary written for a caseworker — the claim details, the single rule that
tripped, and the six checks that passed — followed by the audit trail:

```
--- WHAT THE AGENT DID ---
  Started on claim_1002_high_value.txt
  Read 897 characters from the document.
  Found: claim_id, claimant_name, policy_number, claim_amount
  Ran 8 rules, 1 failed.
  Decision: NEEDS_REVIEW
  Drafted the document for a caseworker to sign.
```

### Step 3 — Sign off as a caseworker

```bash
python3 -m claimflow review --reviewer "Your Name"
```

Approve the first claim, reject the second with a reason, then type `quit`. Expect:

```
Saved. CLM-1002 was approved by Your Name.
Saved. CLM-1003 was rejected by Your Name.
```

### Step 4 — Confirm the decisions survived

This is a **separate command**, so a new process reads the queue from disk:

```bash
python3 -m claimflow list
```

All six claims are listed. The rows that changed:

```
CLM-1002       APPROVED BY HUMAN    $18,500.00  ...
CLM-1003       REJECTED BY HUMAN     $3,150.00  ...
CLM-1005       NEEDS REVIEW          $2,300.00  ...   ← you skipped this one
```

**What this proves:** the halt is durable. The agent finished and exited, and the waiting work is
still there.

Now look at the rejected claim:

```bash
python3 -m claimflow show CLM-1003
```

The exception summary has been replaced by a real rejection letter carrying the reason the
caseworker typed.

### Step 5 — Check the PDF and scanned claims

Skip this step if your claims only ever arrive as text. Otherwise install the extras first
([B1](#b1-prerequisites)):

```bash
pip install claimflow[ocr]
sudo apt install tesseract-ocr
python3 -m claimflow run samples_pdf/
```

```
CLAIM          STATUS                   AMOUNT  WHY
------------------------------------------------------------------------------
CLM-2001       REJECTED             $12,400.00  The claim asks for $12,400.00 but the policy only cover...
CLM-2002       NEEDS REVIEW          $3,150.00  This document was a scan with no text in it, so the fig...

2 claims processed. 1 waiting for a human.
```

Two different documents. `CLM-2001` is a PDF with real text inside it, read directly. `CLM-2002`
is a genuine scan — a picture with no text at all — so it was read by OCR. Confirm the agent says
so:

```bash
python3 -m claimflow show CLM-2002
```

```
  Read 540 characters from the document.
  The PDF had no text layer, so OCR read 1 scanned page(s).
```

**What this proves:** scanned claims are read, and are then held back for a person. Every other
check on `CLM-2002` passed — the only reason it stopped is that a machine guessed at the figures.

Without the extras installed, neither claim crashes the run. Both report `COULD NOT READ` with
the exact command to fix it. That is also correct behaviour.

### Step 6 — Run the tests

```bash
python3 -m unittest discover tests
```

```
Ran 28 tests in 2.289s

OK (skipped=2)
```

The skip count depends on what is installed, and skips are expected either way:

| What you have installed | Expect |
|---|---|
| Nothing extra | `OK (skipped=6)` — the PDF and OCR tests cannot run |
| `pypdf` only | `OK (skipped=5)` |
| `claimflow[ocr]` and Tesseract | `OK (skipped=2)` — the two that remain only check the *missing library* messages, so they skip once the libraries are there |

Anything other than `OK` is a failure. Escalate to engineering.

### Step 7 — Clean up

```bash
rm -rf queue
```

## A2. Where each requirement in the brief lives

| The brief asks for | Where it is in the code |
|---|---|
| A multi-step agent flow | `claimflow/agent.py:75` — the five steps, in order |
| Custom Python orchestration | `claimflow/agent.py:78` — `run_one`, 30 lines |
| Extract Name, Amount, Policy Number | `claimflow/extract.py:8` patterns, `claimflow/extract.py:68` extractor |
| Check against a business rule set | `claimflow/rules.py` — eight rules |
| HITL trigger: claim over $10,000 | `claimflow/rules.py:4` — `AUTO_APPROVE_LIMIT` |
| HITL trigger: conflicting data | `claimflow/models.py:42` — one line |
| Agent halts | `Status.NEEDS_REVIEW`, written to disk rather than raised as an error |
| Drafts an exception review summary | `claimflow/letters.py` — the `EXCEPTION` template |
| Human sign-off | `claimflow/store.py:61` — `record_decision` |
| Error handling | `claimflow/agent.py:78` — a `try` around every step |
| State management | `claimflow/store.py` — one JSON file per claim |

One thing goes beyond the brief: **scanned documents**. Claims that arrive as pictures rather
than text are read by OCR (`claimflow/ocr.py`) and then always held for a human
(`claimflow/rules.py` — `text_is_machine_readable`). Step 5 above verifies it.

## A3. What is not in this repository

The 3-minute video walkthrough is a separate deliverable. The README has a timed running order
for it under "Suggested 3-minute demo".

---

# PART B — Operate this system

## B1. Prerequisites

| What | Requirement |
|---|---|
| Python | 3.8 or newer. Built and tested on 3.10. |
| Libraries | **None** for text claims. |
| PDF claims | `pip install pypdf` — only if your claims arrive as PDFs. |
| Scanned claims | `pip install claimflow[ocr]` **and** `sudo apt install tesseract-ocr` — only if those PDFs are pictures rather than text. |
| Where you run it | From the repository folder. |

Check Python before anything else:

```bash
python3 --version
```

If you would rather run `claimflow` from anywhere instead of `python3 -m claimflow`, install it
once with `pip install .` from the repository folder. Every command below works either way.

## B2. First-time setup

```bash
git clone <this-repo>
cd casestudy
mkdir -p inbox archive
```

- `inbox/` — new claim documents land here
- `archive/` — documents already processed
- `queue/` — the agent creates this itself on the first run

Now run the health check in [B7](#b7-health-check). Do not process real claims until it passes.

## B3. The daily cycle

```
   inbox/   →   run   →   archive/        each document is processed exactly once
                 ↓
              queue/                      the agent's memory, one file per claim
```

> ### ⚠ Never run `run` twice over the same document
>
> `run` writes a fresh result for every document it reads. If a caseworker already approved
> CLM-1002 and you run the same file again, that claim goes straight back to **NEEDS REVIEW** and
> the sign-off is gone.
>
> This is real. Approve a claim, re-run, and you will watch `APPROVED BY HUMAN` turn back into
> `NEEDS REVIEW`.
>
> **Step 4 below is what prevents it.** Do not skip it.

### The checklist

**1. Put new documents in the inbox.**

```bash
cp /path/to/new/claims/*.txt inbox/
```

Anything the agent can read may go in: `.txt`, `.text` and `.pdf`. Any other file type is
ignored when you point `run` at a folder.

**2. Run the agent.**

```bash
python3 -m claimflow run inbox/
```

**3. Read the results before moving on.**

Look for `COULD NOT READ` rows and deal with them now — see [B9](#b9-troubleshooting). Do not
judge the run by whether the command succeeded: **a run containing unreadable documents still
exits with code 0.** Your eyes on the table are the check, not the exit code.

**4. Move the processed documents to the archive.** ← *never skip this*

```bash
mv inbox/* archive/
```

The inbox is now empty, so tomorrow's run cannot touch today's claims.

**5. Hand over to the caseworker.** They clear the queue — see [B4](#b4-clearing-the-review-queue).

**6. Check the queue is clear at end of day.**

```bash
python3 -m claimflow list
```

Nothing should still say `NEEDS REVIEW`. Anything left is work carried into tomorrow.

**7. Back up the queue.** See [B6](#b6-backup-recovery-and-rollback).

## B4. Clearing the review queue

This is the caseworker's job.

```bash
python3 -m claimflow review --reviewer "Your Name"
```

Always pass `--reviewer` with your real name. It is written into the permanent record of the
claim.

The agent shows you one claim at a time and asks:

```
approve / reject / skip / quit >
```

| You type | What happens |
|---|---|
| `approve` or `a` | The claim is approved. An approval letter is written. |
| `reject` or `r` | The claim is rejected. A rejection letter is written. |
| `skip` or `s` or just Enter | Nothing changes. The claim stays in the queue for later. |
| `quit` or `q` | Stop here. Everything already decided is saved. |

After approve or reject you are asked for a reason. It is optional, but **type one for every
rejection** — your words go into the letter the claimant receives.

You can stop any time. Each decision is written to disk the moment you make it, so quitting
halfway never loses the work you have done.

## B5. Status reference

| Status on screen | What it means | Who acts next |
|---|---|---|
| `APPROVED` | Every rule passed. The agent decided alone. | Nobody. Sign the letter and pay. |
| `REJECTED` | A blocking rule failed — lapsed policy, unknown policy, or over the coverage limit. | Nobody. Sign and send the letter. |
| `NEEDS REVIEW` | The agent stopped. Too big, contradictory, missing a fact, or read off a scan by OCR. | **Caseworker.** Run `review`. |
| `COULD NOT READ` | The document could not be opened, had no text, or needed a library that is not installed. No claim was assessed. | **Operator.** See [B9](#b9-troubleshooting). |
| `APPROVED BY HUMAN` | A caseworker approved it. | Nobody. Closed. |
| `REJECTED BY HUMAN` | A caseworker rejected it. | Nobody. Closed. |

`COULD NOT READ` is the one to watch. It does not mean the claim was denied — it means the claim
was **never assessed at all**. Those documents need a person.

## B6. Backup, recovery and rollback

`queue/` holds every decision the system has made. It is the only folder that matters, and it is
deliberately not stored in git.

**Back up at the end of every working day:**

```bash
cp -r queue backups/queue-$(date +%F)
```

**Recover everything** — restore the whole folder:

```bash
rm -rf queue && cp -r backups/queue-2026-08-06 queue
```

**Roll back one wrong decision** — restore just that claim:

```bash
cp backups/queue-2026-08-06/CLM-1002.json queue/CLM-1002.json
```

**A claim cannot be decided twice.** `review` only ever offers claims that are still waiting, so
in normal use two caseworkers will not collide. Underneath that, the storage layer refuses a
second decision outright:

```
Error: Claim CLM-1002 is already HUMAN_APPROVED.
```

You are unlikely to ever see this message. It is the backstop for the narrow case where two
people are reviewing at the exact same moment. It means someone else already decided that claim —
run `show <REF>` to see who and when. To genuinely change a settled decision, restore that
claim's file from backup first.

## B7. Health check

Run this after installing, after any rule change, and any time behaviour looks wrong.

**1. The tests:**

```bash
python3 -m unittest discover tests
```

Expect `Ran 28 tests` and `OK`. The skip count depends on which optional libraries you have —
see the table in [A1 Step 6](#step-6--run-the-tests). Anything other than `OK` — stop and
escalate to engineering.

**2. The known claims**, into a scratch queue so live work is untouched:

```bash
python3 -m claimflow --queue /tmp/healthcheck run samples/
rm -rf /tmp/healthcheck
```

All six outcomes must match exactly:

| Claim | Must say |
|---|---|
| CLM-1001 | APPROVED |
| CLM-1002 | NEEDS REVIEW |
| CLM-1003 | NEEDS REVIEW |
| CLM-1004 | REJECTED |
| CLM-1005 | NEEDS REVIEW |
| claim_1006 | COULD NOT READ |

If any row differs, something changed that should not have. Do not process live claims.

**3. The PDF and scanned claims** — only if you process PDFs:

```bash
python3 -m claimflow --queue /tmp/healthcheck run samples_pdf/
rm -rf /tmp/healthcheck
```

| Claim | Must say |
|---|---|
| CLM-2001 | REJECTED |
| CLM-2002 | NEEDS REVIEW |

If `CLM-2002` says `APPROVED`, stop immediately and escalate. A scanned claim must never be
auto-approved — that would mean the `text_is_machine_readable` rule is no longer firing.

## B8. Changing the rules

Business rules change. Follow this sequence every time — never edit and go straight to live work.

### Changing the money threshold

Open `claimflow/rules.py`, line 4:

```python
AUTO_APPROVE_LIMIT = 10_000
```

Change the number. That is the whole edit. Every letter and every summary picks up the new figure
automatically.

### Adding or updating a policy

Open `policies.json`. Each entry looks like this:

```json
"POL-889231": {
  "holder": "Maria Gonzalez",
  "status": "active",
  "coverage_limit": 50000
}
```

- `holder` — must match the name on the claim, or the agent stops for review
- `status` — anything other than `active` causes rejection
- `coverage_limit` — a claim above this is rejected

Commas between entries, no comma after the last one. A missing comma will stop the tool loading.

### The required sequence

1. Make the change
2. Run the health check ([B7](#b7-health-check))
3. Run the samples into a scratch queue and confirm the new figure appears in the letters
4. Only then use it on live claims

Changes take effect on the **next** run. Claims already in the queue keep the decision they were
given under the old rules.

## B9. Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| `No module named claimflow` | You are in the wrong folder. | `cd` to the repository folder and try again. |
| `This is a PDF, and reading PDFs needs an extra library.` | A PDF arrived and `pypdf` is not installed. | `pip install pypdf`, then run again. |
| `The file opened but had no text in it.` | A blank file. | The claim was **not** assessed. Get a better copy, or process it by hand. |
| `This PDF has no text layer, so it has to be read by OCR.` | A scanned PDF arrived and the OCR libraries are not installed. | `pip install claimflow[ocr]`, then run again. |
| `This PDF needs OCR, and the Tesseract program itself is missing.` | The Python packages are installed but the OCR program behind them is not. | `sudo apt install tesseract-ocr`, then run again. |
| `This PDF has no text in it and no pictures we could read.` | A PDF drawn as vector graphics — no text layer and no scanned image. OCR cannot help. | The claim was **not** assessed. Ask the provider for the original, or process it by hand. |
| A scanned claim always says NEEDS REVIEW | Working as designed. The `text_is_machine_readable` rule stops every OCR'd claim. | Check the figures against the paper copy, then `review` it. |
| `Cannot read '.json' files. We handle: .pdf, .text, .txt` | A file type we do not support ended up in the inbox. | Remove it from `inbox/`. Only claim documents belong there. |
| `Error: There is nothing at '/path'.` | The path is wrong or the folder was moved. | Check the path. Run `ls` on it. |
| `Error: No saved claim called 'CLM-9999'.` | That claim is not in the queue. | Run `list` to see the real references. Check you are using the right `--queue`. |
| `Error: Claim CLM-1002 is already HUMAN_APPROVED.` | Rare. Two people were reviewing at the same moment and someone else decided this claim first. | Not a fault — the record was protected. Run `show <REF>` to see who decided it. To change it, restore from backup — [B6](#b6-backup-recovery-and-rollback). |
| `The queue at 'queue' is empty.` | Nothing has been processed, or you are pointed at the wrong queue folder. | Run `run` first, or check your `--queue` value. |
| `Policy POL-XXXXXX is not in our records.` | The policy is missing from `policies.json`. | If the policy is genuine, add it — [B8](#b8-changing-the-rules). If not, the rejection is correct. |
| A claim you expected to be approved says `NEEDS REVIEW` | A rule stopped it. | Run `show <REF>` and read "WHY THE AGENT STOPPED". It always says which rule and why. |
| A caseworker's decision has disappeared | `run` was executed again over an archived document. | Restore that claim from backup ([B6](#b6-backup-recovery-and-rollback)), then follow [B3](#b3-the-daily-cycle) step 4 from now on. |

## B10. Escalation

Fill in the contacts before handing this to the operations team.

| Tier | Who | Handles | Contact |
|---|---|---|---|
| 1 | Caseworker | Anything in the review queue. Approving and rejecting. | *(fill in)* |
| 2 | Claims supervisor | Whether a rule is right. Disputed decisions. Adding policies. Changing the threshold. | *(fill in)* |
| 3 | Engineering | Crashes. Failed health checks. Documents that will not parse. Lost decisions. | *(fill in)* |

**Before you escalate to Tier 3, gather:**

1. The claim reference, for example `CLM-1002`
2. The full output of `python3 -m claimflow show <REF>` — this includes the audit trail
3. The original document from `archive/`
4. Exactly what you typed and exactly what appeared on screen

Anything involving money moving, or a claimant already told the wrong outcome, goes to Tier 2
immediately. Do not wait.

---

# Appendix

## Exit codes

| Code | Meaning |
|---|---|
| `0` | The command ran. **This includes runs where some documents could not be read.** |
| `1` | No claim files were found at the path, or the command failed with a message starting `Error:`. |

If you automate this on a schedule, do **not** treat exit code `0` as "everything is fine". Check
the output for `COULD NOT READ` rows.

## Where files live

| Folder | Holds | In git? |
|---|---|---|
| `inbox/` | Documents waiting to be processed | No |
| `archive/` | Documents already processed | No |
| `queue/` | Agent state, one JSON file per claim | No — this is your live data |
| `samples/` | Six example claims used by the health check | Yes |
| `samples_pdf/` | One PDF with a text layer, one genuine scan | Yes |
| `tools/` | Rebuilds the scanned sample. Never needed to run the agent. | Yes |
| `policies.json` | The policy records | Yes |

Queue files are named after the claim reference: `queue/CLM-1002.json`. If a document has no
claim reference in it, the file name is used instead.

## Command reference

| Command | What it does |
|---|---|
| `python3 -m claimflow run <path>` | Read every claim at a file or folder and decide on them |
| `python3 -m claimflow list` | Show every claim in the queue and its status |
| `python3 -m claimflow show <REF>` | Print one claim's letter and full audit trail |
| `python3 -m claimflow review` | Work through the claims waiting for a human |

| Flag | Use |
|---|---|
| `--queue <folder>` | Use a different queue. Use this for tests so live data is untouched. |
| `--policies <file>` | Use a different set of policy records. |
| `--reviewer "Name"` | Sign your decisions. Use with `review`. |

Add `--help` to any command to see its options.
