# TrustOps v0 — Evidence-Gated Security Questionnaire Engine

**Every answer cited to a versioned, approved source — or refused.** A working demonstration of applied AI inside a GRC control plane: grounded generation, deterministic guardrails, abstention-by-design, tamper-evident audit trail, and an adversarial eval suite that blocks release on any unsupported claim.

Built as v0 of TrustOps Desk (managed customer assurance for B2B SaaS). All data is synthetic.

## What it proves

Most RAG demos answer confidently. This one **refuses correctly** — which is the property that matters when the output is a material security representation in an enterprise deal.

| Run metric (24-question CAIQ-style run) | Result | Gate |
|---|---|---|
| Cited draft coverage | **70.8%** | ≥60% target |
| Unsupported material claims | **0** | must be 0 — release blocker |
| Refusals (abstain/route) | 29.2% | every one names its gap and its human route |
| Audit chain | valid | hash-chained JSONL, tamper detection tested |
| Structure round-trip | pass | merged cells, hidden rows, formulas survive export |

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

Key design decision: **the gates do not trust the drafter.** Swapping the deterministic `MockDrafter` for the live `AnthropicDrafter` changes fluency, not safety posture. Tenant isolation, forbidden claims, staleness, and approval are enforced in code, not prompt.

## Run it

```bash
python3 data/make_questionnaire.py        # regenerate source questionnaire
python3 run_demo.py --today 2026-08-08    # offline deterministic run
python3 -m pytest tests/ -q               # adversarial eval suite (11 tests)

export ANTHROPIC_API_KEY=...              # live LLM drafting under the
python3 run_demo.py --drafter anthropic   # Appendix-B system contract
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
- Contradiction detection uses declared machine-checkable assertions; NLI-based detection is future work.

## Roadmap

See `docs/TRUSTOPS_V0.md` for the phased build directive (live-drafter evals, Streamlit review queue, semantic retrieval, portal ingestion).

---
*Synthetic data only. Nothing in this repository derives from any client engagement.*
