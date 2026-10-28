# Constat

**Every security answer rests on an owned, expiring, exception-carrying claim, or it is refused and routed to the person who can fix it.**

Constat drafts answers to customer security questionnaires from a claim store, gates every draft deterministically, and ships nothing without a person. It runs standalone, and it installs inside Atlan as an embedded app with the claims in Atlan's own glossary.

[![ci](https://github.com/dhruvshahi10/constat/actions/workflows/ci.yml/badge.svg)](https://github.com/dhruvshahi10/constat/actions/workflows/ci.yml) MIT licence.

## What the code backs (28 Oct 2026)

| Check | Result |
| --- | --- |
| Test suite | 348 tests passing |
| Golden set (`evals/golden`) | 30 cases, 0 dangerous failures, weighted 1.0 |
| Injection suite (`evals/injection`) | 40 cases, all quarantined or refused |
| Gate branch coverage | 98% |
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

**Gates** (`constat/claims/gates.py`), in order: injection, legal, no covering claim, claim status and freshness and audience, certification evidence class, relevance, parameter missing, completeness (every exception appears), absolutes, new values, contractual wording. Each verdict carries a difficulty class: reused, covered, parameter missing, novel, contractual.

**Hard limits** that never automate: new contractual commitments, first-time questions, disclosing sensitive internals, publishing to the public trust centre, correcting or declining a customer live.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q
CONSTAT_ENV=dev CONSTAT_DEV_TOKEN=dev DATABASE_URL=sqlite:///data/sidecar.db CLAIM_STORE_PATH=data/claims \
  .venv/bin/python scripts/seed_demo.py --tenant acme
CONSTAT_ENV=dev CONSTAT_DEV_TOKEN=dev DATABASE_URL=sqlite:///data/sidecar.db CLAIM_STORE_PATH=data/claims \
  .venv/bin/uvicorn api.main:app --port 8000
cd web && npm ci && NEXT_PUBLIC_API_BASE=http://localhost:8000 NEXT_PUBLIC_DEV_TOKEN=dev npm run dev
```

Open http://localhost:3000/review. `docs/demo-script.md` is the three-minute walkthrough.

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
- Docx questionnaires have no row identity, so export is a new file.
- The regex gates see canonical text (NFKC, zero-width stripped, number words as digits) but remain lexical; they catch fabrication, omission, absolutes and evasion by spacing or homoglyphs, not every paraphrase. Every ANSWER still goes to a person.
- The Vanta response shape and the App Framework SDK names are taken from public docs and are not yet verified against a live tenant.
