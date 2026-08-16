# TrustOps v0 — Evidence-Gated Security Questionnaire Engine

[![evals](https://github.com/dhruvshahi10/trustops/actions/workflows/ci.yml/badge.svg)](https://github.com/dhruvshahi10/trustops/actions/workflows/ci.yml) [![license: MIT](https://img.shields.io/badge/license-MIT-1E6B47.svg)](LICENSE)

**Every answer cited to a versioned, approved source — or refused.** A working demonstration of applied AI inside a GRC control plane: grounded generation, deterministic guardrails, abstention-by-design, tamper-evident audit trail, and an adversarial eval suite that blocks release on any unsupported claim.

Built as v0 of TrustOps Desk (managed customer assurance for B2B SaaS). All data is synthetic.

## What it proves

Most RAG demos answer confidently. This one **refuses correctly** — which is the property that matters when the output is a material security representation in an enterprise deal.

| Run metric (24-question CAIQ-style run, **deterministic mock drafter**) | Result | Gate |
|---|---|---|
| Cited draft coverage | **66.7%** | ≥60% target |
| Refusals (abstain/route) | 33.3% | every one names its gap and its human route |
| Answers refused as ungrounded | **1** | words not traceable to the cited passage |
| Citations dropped by the gates | 0 | fabricated source, invented location, or never retrieved |
| Audit chain | valid | hash-chained JSONL, tamper detection tested |
| Structure round-trip | pass | merged cells, hidden rows, formulas survive export |

Two notes on reading this table honestly. Every figure comes from the deterministic
mock drafter; no live-model run has been measured yet, so these numbers describe the
gates, not a model's accuracy. And coverage fell from an earlier 70.8% on purpose: a
new grounding gate now refuses an answer whose own words are not traceable to the
passage it cites, and it caught one answer that had been drafted from evidence the
staleness gate then removed. That answer used to ship as cited. It no longer does.

## The four planted traps — and what happened

1. **Certification inference.** Q: "Are you ISO 27001 certified?" Evidence: only a roadmap. → **Abstained.** Certification claims require evidence of type `certificate`/`attestation`; plans never qualify.
2. **Contradiction.** Two approved policies assert 90 vs 365 days for customer-data deletion. → **Both quarantined**, question routed to both source owners. Second-order effect: a *different* question that would have cited the deletion policy also refused.
3. **Stale evidence.** Pentest report expired 2025-06-10. → Flagged `STALE_EVIDENCE`, no current-testing claim released, routed to owner.
4. **Legal commitment.** Buyer demands unlimited liability + uptime guarantees. → Routed to LEGAL *before* drafting. The model never sees it as an answerable question.

Plus: cross-tenant isolation (a semantically similar decoy tenant exists; zero leakage, mismatch raises `PermissionError`) and audit-log tampering (chain verification fails on any edited historical event).

## Architecture

```
questionnaire.xlsx
      │  ingest (row identity preserved)
      ▼
RECEIVED → CLASSIFIED → DRAFTED → [EXCEPTION | GRC_REVIEW] → DELIVERED
      │            │         │              │                    │
      │       pre-gates   drafter      post-gates          export back into
      │       (legal,    (mock or     (cite-or-abstain,    original XLSX,
      │        cert tag)  Claude)      stale, contradiction, structure intact
      │                                cert evidence class)
      └────────── hash-chained append-only audit log ──────────┘
```

Key design decision: **the gates do not trust the drafter.** Swapping the deterministic `MockDrafter` for a live model (`GeminiDrafter`, `AnthropicDrafter`) changes fluency, not safety posture. Tenant isolation, forbidden claims, staleness, and approval are enforced in code, not prompt.

## Client console

![TrustOps console](docs/ui.png)

A zero-dependency web UI ([ui/app.py](ui/app.py), Python stdlib only — no framework, no build step). Ask a single security question through the full gate path — refusals render as first-class outcomes with the gap named — or run the whole 24-question workbook and download the audit working paper, the DELIVERED workbook, and the hash-chained audit log. Sample outputs live in [examples/](examples/).

## Run it

```bash
# one-time setup (Python 3.10+; only pytest + openpyxl are installed)
python3 -m venv .venv && .venv/bin/pip install pytest openpyxl

.venv/bin/python -m pytest tests/ -q              # adversarial eval suite (11 tests)
.venv/bin/python data/make_questionnaire.py       # regenerate source questionnaire
.venv/bin/python run_demo.py                      # offline deterministic run
.venv/bin/python ui/app.py                        # web console → http://localhost:8787

export GEMINI_API_KEY=...                         # free key: aistudio.google.com
.venv/bin/python run_demo.py --drafter gemini     # live LLM run at $0 (stdlib REST, no SDK)

export ANTHROPIC_API_KEY=...                      # default model: Haiku 4.5 —
.venv/bin/python run_demo.py --drafter anthropic  # gates make the cheap model safe
```

Outputs per run (`runs/<stamp>/`): `run_report.html` (audit working paper), `<name>__DELIVERED.xlsx`, `contracts.json` (machine-readable answer contracts), `metrics.json`, `audit_log.jsonl`.

## Answer contract

```json
{"question_id": "...", "answer": "...|null",
 "citations": [{"source_id": "...", "version": "...", "location": "para:2"}],
 "evidence_coverage": "complete|partial|none", "risk": "low|medium|high",
 "gaps": ["..."], "requires_human": true}
```

Coverage is derived from citations that **survived the gates** — model confidence never overrides missing evidence.

## Honest limitations (v0)

- Retrieval is lexical (transparent, reproducible). One question (`IVS-01.1`, hosting regions) abstained on a retrieval miss rather than answering — fail-closed as designed. Semantic retrieval is the v1 upgrade and does not change the gates.
- Demo runs use a *labeled, simulated* reviewer that approves only gate-clean, complete-coverage drafts; production requires interactive named-human sign-off.
- Contradiction detection uses declared machine-checkable assertions; NLI-based detection is future work. On uploaded documents those assertions are extracted from prose, and the extractor is deliberately narrow: it ignores anything that is not the vendor's own commitment (quoted law, a subprocessor's duty, an obligation on the customer) because a false assertion manufactures a false contradiction and quarantines a perfectly good source. Hedged prose is skipped too, so a real corpus yields fewer contradictions than the synthetic sample pack demonstrates.
- **The grounding gate is lexical, not semantic.** It checks that an answer's words are traceable to the passage it cites, which catches fabricated citations and answers that drift off their source. It does not understand meaning: an answer that reuses a passage's vocabulary while inverting it ("data is *not* encrypted at rest") still passes. The 0.35 threshold was calibrated against the deterministic mock drafter, which quotes chunk text verbatim and is therefore trivially grounded; it has not been calibrated against a live model that paraphrases, and a model that summarizes policy prose into plain business language will trip it. Expect a higher abstention rate on the first live run, attributable to the gate rather than to missing evidence.

## Roadmap

See `docs/TRUSTOPS_V0.md` for the phased build directive (live-drafter evals, Streamlit review queue, semantic retrieval, portal ingestion).

---
*Synthetic data only. Nothing in this repository derives from any client engagement.*
