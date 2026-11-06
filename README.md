# Constat

**Every security answer rests on an owned, expiring, exception-carrying claim, or it is refused and routed to the person who can fix it.**

Constat drafts answers to customer security questionnaires from a claim store, gates every draft deterministically, and ships nothing without a person. It runs standalone, and it installs inside Atlan as an embedded app with the claims in Atlan's own glossary.

[![ci](https://github.com/dhruvshahi10/constat/actions/workflows/ci.yml/badge.svg)](https://github.com/dhruvshahi10/constat/actions/workflows/ci.yml) MIT licence.

## What the code backs (6 Nov 2026)

| Check | Result |
| --- | --- |
| Test suite | 429 Python tests passing, including the Postgres path against a real Postgres; 12 web unit tests; 91 Playwright tests (smoke, CSP, handshake, both themes at 1440 and 390) |
| Golden set (`evals/golden`) | dev split 41 cases, 0 dangerous failures, weighted 1.0; holdout 11 cases, 0 dangerous, reported and never tuned against |
| Injection suite (`evals/injection`) | 44 cases (4 laid out as PDF lines), all quarantined or refused |
| Claim-drafting set (`evals/author`) | 18 cases, 0 dangerous: no instruction, plan or marketing drafted, no exception dropped |
| Gate branch coverage | 99% on `constat/claims/gates.py` (CI floor 95%) |
| Install smoke (`scripts/smoke.py`) | 12 of 12 checks over real HTTP against a fresh install |
| Load (`scripts/load_test.py`) | 200 questions in about 0.4 s with the deterministic drafter |

Live-model figures: the GitLab CAIQ field test on 29 Aug 2026 (54 controls, Gemini, public handbook only) answered 31.5% with citations and 0 unsupported claims; a model-evaluation record for Claude Haiku 4.5 is produced by `evals/run_live.py` and is required by CI for any model or prompt change.

## How it works

```
file or portal export ─► parsers ─► normaliser (model, no tools, canary) ─► quarantine
        │
        ▼
items (state machine) ─► match to claims ─► draft on one claim ─► gates ─► REVIEW | HELD | REFUSED
        │
        ▼
review queue (ranked) ─► approve / edit / route / send ─► writeback to claims ─► sent-answer record
        │
        ▼
metrics by difficulty class · degradation · automation ladder · trust preview · model-eval records
```

**Claims** (`constat/claims/`): statement, a person as owner, evidence refs (Vanta test, policy, certificate), scope, a list of exceptions, audience, validity window, content-hash version, approved answers. Stores: file (local), Atlan glossary plus custom metadata through pyatlan.

**Gates** (`constat/claims/gates.py`), in order: injection, legal, no covering claim, claim status and freshness and audience, product scope (a catalog claim never answers for AI features or the MCP server; a metadata claim never answers for customer data), certification evidence class, relevance (the property asked about and the thing it is asked of are judged apart), parameter missing, completeness (every exception appears), absolutes, new values, contractual wording. Each verdict carries a difficulty class: reused, covered, parameter missing, novel, contractual. Every ANSWER also carries a computed confidence (relevance, evidence class, freshness, provenance, each with its reason); it orders review and never changes an outcome.

**Knowledge layer.** Claims carry the products, deployment and data classes they are true for (`constat/claims/scope.py`). `POST /v1/claims/author` and the `/claims/author` screen turn a policy or docs page (pasted, or pdf, docx, md, txt) into draft claims, one fact each, each quoting the exact source span; a second person approves every one. Questionnaires arrive as xlsx, csv, docx or pdf.

**Import.** `POST /v1/claims/import` turns a questionnaire already answered and sent into proposed claims and reusable answers; a person commits, and every new claim is a draft a second person approves.

**Hard limits** that never automate: new contractual commitments, first-time questions, disclosing sensitive internals, publishing to the public trust centre, correcting or declining a customer live.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q
CONSTAT_ENV=dev CONSTAT_DEV_TOKEN=dev CONSTAT_TENANT=acme DATABASE_URL=sqlite:///data/sidecar.db CLAIM_STORE_PATH=data/claims \
  .venv/bin/python scripts/seed_demo.py --tenant acme
CONSTAT_ENV=dev CONSTAT_DEV_TOKEN=dev CONSTAT_TENANT=acme DATABASE_URL=sqlite:///data/sidecar.db CLAIM_STORE_PATH=data/claims \
  .venv/bin/uvicorn api.main:app --port 8000
cd web && npm ci && NEXT_PUBLIC_API_BASE=http://localhost:8000 NEXT_PUBLIC_DEV_TOKEN=dev npm run dev
```

Open http://localhost:3000/review. `docs/demo-script.md` is the three-minute walkthrough.

## Road to completion

`docs/ROADMAP.md` checks the plan's definition of done item by item with evidence, and lists what only a person can do next (merge, live model evaluation, hosted deploy, runbook dry run, the Atlan tenant, a case study).

## Install on an Atlan tenant

`docs/runbooks/fde-install.md`, with `rollback.md` and `degradation.md` beside it. `scripts/atlan_setup.py` prepares the glossary, the "Claim" custom metadata set and the terms. The web app embeds under `/embed/*` with a postMessage handshake that accepts only the framing window on configured origins. `apps/atlan-app/` wraps the pipeline as an App Framework app. `mcp_server/` exposes six tools for agents; writes are proposals.

## Layout

```
constat/   engine: claims, intake, workflow, persist, integrations; the v0 document pipeline (constat/*.py) and the frozen legacy server (constat/server/)
api/       FastAPI adapter; auth (bearer, Atlan JWT), questionnaires, review, claims, metrics, degradation, trust, evals, webhooks
web/       Next.js app, two themes (constat dark, native light), embedded views, shell simulator
apps/      App Framework wrapper        mcp_server/  MCP server        evals/  golden set, injection suite, live runner, records
scripts/   seed_demo, atlan_setup, principals, load_test, check_eval_record     docs/runbooks/  install, rollback, degradation
```

`DECISIONS.md` is append-only and names the alternative rejected for every architectural choice. `tests/test_gates.py` is the v0 constitution and is never edited without a DECISIONS entry.

## Known limits

- Portal intake (Archer, OneTrust, ProcessUnity) is export and import; no browser automation.
- Docx and PDF questionnaires have no row identity, so export is a new file (a csv of answers). Scanned PDFs need OCR, which is not supported.
- The regex gates see canonical text (NFKC, zero-width stripped, number words as digits) but remain lexical; they catch fabrication, omission, absolutes and evasion by spacing or homoglyphs, not every paraphrase. Every ANSWER still goes to a person.
- The Vanta response shape, the App Framework SDK names and the multi-valued Options attributes for products and data classes are taken from public docs and are not yet verified against a live tenant.
- Product scope and the property families behind the relevance gate are closed vocabularies; a product or property they do not list is not detected, which is the behaviour from before they existed. Extend `constat/claims/scope.py` and `constat/claims/properties.py` with golden cases.
- Confidence weights are a starting point; calibrate them against reviewer edit rates per band once a tenant has four weeks of metrics.
- No model-evaluation record exists yet for Claude Haiku 4.5: it needs an Anthropic key (`evals/run_live.py`). Until the first record is committed, the CI eval-record gate is advisory. That includes the claim-drafting assistant's Haiku variant (`constat/claims/author.py`), which is tested offline only; the deterministic extractor is the default.
