# Pramana — evidence-gated customer assurance

[![evals](https://github.com/dhruvshahi10/pramana/actions/workflows/ci.yml/badge.svg)](https://github.com/dhruvshahi10/pramana/actions/workflows/ci.yml) [![license: MIT](https://img.shields.io/badge/license-MIT-1E6B47.svg)](LICENSE)

**Live: [pramana-red.vercel.app](https://pramana-red.vercel.app)** · [Our own trust center](https://pramana-red.vercel.app/trust/) · [Published accuracy](https://pramana-red.vercel.app/accuracy/) · [Try it](https://pramana-red.vercel.app/demo/)

Every answer cited to a versioned, approved source — or refused. Pramana deflects the buyer
questions it can answer from evidence, answers the ones that reach a questionnaire, and refuses
the rest by name.

*Formerly TrustOps. All client data in this repository is synthetic.*

---

## The number

| [59 adversarial prompts](evals/adversarial.json) | Result |
|---|---|
| Correctly refused | **42/44 (95.5%)** |
| Correctly cited | **11/15 (73.3%)** |
| Released with **no citation** | **0** — the release gate |
| Over-released (answered where refusal was required) | **2** |

Two numbers, not one: refusing everything scores 100% on the first and is useless; answering
everything scores 100% on the second and is dangerous. Labels were written before the harness
first ran and none was revised to match the result. **Every failure is published by name** —
[method and failures](https://pramana-red.vercel.app/accuracy/), [docs/accuracy.md](docs/accuracy.md).

The suite has already caught two real bugs in this engine. The certification gate matched an
allowlist of scheme names that did not include ISO 42001, so a *roadmap* satisfied an ISO 42001
certification question on our own trust page. And nothing stopped the engine answering "what does
Globex's policy say?" out of a different client's corpus — no data leaked, but one company's
controls were being attributed to another. Both are fixed; both are in the changelog.

## What it does, in the order that matters

**1 · Deflect.** Generate a self-service trust center from the evidence corpus. Every question a
buyer answers themselves never reaches your security team.

**2 · Answer.** What the trust page can't deflect is drafted from approved, in-force sources —
cited to source id, version and paragraph — and written back into the buyer's own workbook with
merged cells, hidden rows and formulas intact.

**3 · Refuse.** No evidence, stale evidence, contradictory evidence, a contractual commitment
dressed as a question, or a question about somebody else: the engine declines, names the specific
gap, and routes it to a named human.

Plus a **commitment register** that runs the inverse check — you already promised this in a
contract; can you still stand behind it?

## Answer status, not a confidence score

A score invites shipping a 0.72. A status names what is true about the evidence, and is derived in
code from citations that survived the gates — never from the model's self-report.

`EVIDENCE_BACKED` · `PARTIAL` · `REQUIRES_HUMAN` · `NO_EVIDENCE` · `ROUTED` · `HUMAN_AUTHORED`

`HUMAN_AUTHORED` matters: when a reviewer answers a question the evidence does not support, the
answer is labelled as theirs in the contract and in the delivered workbook. A reader can always
tell which answers the system supported and which a person asserted.

## Architecture

```
questionnaire (any layout — CAIQ, SIG, bespoke, CSV)
      │  ingest — header row and column roles detected, row identity preserved
      ▼
RECEIVED → CLASSIFIED → DRAFTED → [EXCEPTION | GRC_REVIEW] → DELIVERED
      │          │          │             │                      │
      │     pre-gates    drafter     post-gates            written back into
      │     legal        (any model) cite-or-abstain       the original file,
      │     scope/party              staleness             structure intact
      │     cert tagging             contradiction
      │                              cert evidence class
      └────────── hash-chained append-only audit log ──────────────┘
                  (human review extends the same chain)
```

**The gates do not trust the drafter.** Tenant isolation, forbidden claims, staleness and approval
are enforced in code, not in a prompt. Swapping the deterministic drafter for Gemini or Claude
changes fluency, not safety posture — which is the entire point.

## Onboarding a real client

The corpus is the product's only real setup cost. Documents arrive as PDF and Word; the engine
needs governed metadata. This is the path:

```bash
python onboard.py new-tenant --tenant northwind --name "Northwind Health"
python onboard.py stage      --tenant northwind --from data/onboarding_samples/northwind
python onboard.py review     --tenant northwind
python onboard.py promote    --tenant northwind --id POL-ACCESS-CONTROL \
    --actor "Priya Nair <priya@northwind.example>"
```

Two things to watch, because they are the design:

- **Nothing is auto-approved.** Staged sources land as `approval_status: draft`, which the citation
  gate refuses. Promotion needs a named human and is written to a corpus log.
- **`certificate` and `attestation` are never auto-assigned.** They are the only types that satisfy
  the certification gate, so ingestion refuses to hand that key over on a keyword match. The
  bundled `ISO 27001 Certification Roadmap` types as **roadmap** and is flagged for a human; the
  `Data Retention Standard` mentions "certificate of deletion" in its body and still types as
  **standard**.

Then point it at the buyer's actual file — no code change:

```bash
python onboard.py inspect --questionnaire ~/Downloads/buyer-caiq.xlsx   # show detected layout
python run_demo.py --tenant northwind --questionnaire ~/Downloads/buyer-caiq.xlsx
```

## Human sign-off

```bash
python run_demo.py --tenant acme                      # simulated reviewer (labelled as such)
python review.py --run runs/<stamp>-acme-mock list --pending
python review.py --run runs/<stamp>-acme-mock approve --id IAM-01.1 --actor "Priya <priya@acme.com>"
python review.py --run runs/<stamp>-acme-mock export
```

Decisions extend the run's **own** hash chain, so a review cannot be reconciled with its run after
the fact — forging who approved something breaks chain verification, and that is asserted by test.
`approve` is unavailable when the gates released nothing; a reviewer who wants to answer anyway
must `edit`, and the result is labelled `HUMAN_AUTHORED`.

## Trust center and commitment register

```bash
python onboard.py trustpage   --tenant northwind --contact security@northwind.example
python onboard.py commitments --tenant acme
```

The trust page publishes only evidence-backed answers; everything else becomes an open item and an
evidence-collection worklist. Pramana's own trust center answers **24%** of the standard buyer
set — low, and published as-is: ten approved documents and no certifications of any kind. A trust
page answering 33 of 33 would be evidence of the failure mode this product exists to prevent.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

.venv/bin/python -m pytest tests/ -q          # 30 tests: constitution + review + adversarial
.venv/bin/python evals/run_accuracy.py        # score the adversarial suite, publish the number
.venv/bin/python run_demo.py                  # offline deterministic run
.venv/bin/python ui/app.py                    # operator console → http://localhost:8787
.venv/bin/python build_site.py                # regenerate the public site from the engine

export GEMINI_API_KEY=...                     # free key: aistudio.google.com
.venv/bin/python run_demo.py --drafter gemini # live LLM run at $0 (stdlib REST, no SDK)
export ANTHROPIC_API_KEY=...                  # default model: Haiku 4.5
.venv/bin/python run_demo.py --drafter anthropic
```

Per run in `runs/<stamp>/`: `run_report.html` (audit working paper), `<name>__DELIVERED.xlsx`,
`contracts.json`, `metrics.json`, `manifest.json`, `audit_log.jsonl`.

Dependencies are `pytest` and `openpyxl`. Everything else is stdlib on purpose — PDF via the
`pdftotext` binary, DOCX via `zipfile` + `ElementTree`, the console and the serverless functions
via `http.server`, live model calls via `urllib`.

## Honest limitations

- **Operator-run, not self-serve SaaS.** Onboarding a client is a one-time evidence-corpus pass.
  Visitors cannot upload a corpus.
- **Retrieval is lexical.** Transparent and reproducible, but it misses paraphrases — four positive
  controls in the published suite fail for exactly this reason. It fails closed and refuses rather
  than guessing. Semantic retrieval is the next upgrade and does not change the gates.
- **No compound-question handling.** A question mixing a supported clause with an unsupported one
  can be answered on the supported part. Both current over-releases are this.
- **No false-premise detection.** "Given that you are FedRAMP authorized, at which impact level?"
  is not yet rejected on its premise.
- **The scope gate is blunt.** A question naming another workspace is refused, so a buyer whose
  company name matches another client's gets a refusal and a human. Fail-closed, and noisy.
- **The hosted demo is deterministic** and uses synthetic corpora. Live-model runs ship as dated
  artifacts instead.

## Repository

| Path | |
|---|---|
| [`trustops/gates.py`](trustops/gates.py) | the deterministic gates — the product |
| [`trustops/ingest.py`](trustops/ingest.py) | PDF/DOCX/XLSX ingestion, staged for human approval |
| [`trustops/review.py`](trustops/review.py) | named-human sign-off on the run's own hash chain |
| [`trustops/trustpage.py`](trustops/trustpage.py) | trust center generator |
| [`trustops/commitments.py`](trustops/commitments.py) | sales-to-GRC commitment register |
| [`tests/test_gates.py`](tests/test_gates.py) | the constitution — never modified by feature work |
| [`evals/`](evals/) | the adversarial prompt set, harness and published results |
| [`DECISIONS.md`](DECISIONS.md) · [`GOTCHAS.md`](GOTCHAS.md) | append-only build logs |

The Python package is still named `trustops`: renaming it would edit the import lines in
`tests/test_gates.py`, which is the one file feature work may not touch.

---
*Synthetic data only. Nothing in this repository derives from any client engagement.*
*© Arsanyu Technologies Pvt Ltd — MIT.*
