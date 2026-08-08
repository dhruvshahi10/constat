# TRUSTOPS_V0.md — Claude Code Build Directive

**Status:** v0 core is COMPLETE and green (11/11 eval suite). This directive governs everything after.
**Prime rule:** the eval suite is the constitution. Any change that breaks `tests/test_gates.py` is rejected — fix the change, never the test, unless a DECISIONS.md entry authorizes it.

## Phase 0 — Discovery (READ-ONLY, mandatory first session)

Before writing any code: read `README.md`, `trustops/*.py`, `tests/test_gates.py`, one full `runs/<stamp>/` output including `audit_log.jsonl`. Produce a ≤20-line summary of the gate architecture and the answer contract. **No edits in this session.**

## Non-negotiable invariants (CORE — never modified by feature work)

1. Citation-or-abstain: no answer leaves the system without a gate-surviving citation.
2. Certification/attestation claims require source type `certificate|attestation`. Never inferred.
3. Stale or contradicted sources are unciteable everywhere, automatically.
4. Legal/contract-commitment questions route to LEGAL pre-draft.
5. Tenant isolation is structural (store scoping + boundary assertion), never prompt-based.
6. Audit log is append-only and hash-chained; every state transition writes an event.
7. `unsupported_material_claims == 0` is a release blocker.
8. Export writes only response columns; question text, IDs, order, and structure are untouchable.

## Phase 1 — Live drafter hardening (ADAPTER)

- Run `--drafter anthropic` against the same questionnaire; diff verdicts vs mock run.
- Add eval: live drafter output that fails contract parse ⇒ fail-closed abstention (already coded; needs a recorded-fixture test).
- Add per-question token/cost telemetry to `metrics.json`.
- Add Langfuse tracing behind env flag `TRUSTOPS_LANGFUSE=1`. **Gate:** all 11 tests + new fixtures green with live drafter.

## Phase 2 — Review queue UI

- Streamlit app: exception queue, draft approval with named reviewer + note, diff view of reviewer edits (edit distance feeds the reviewer-leverage metric).
- Approval writes the audit event; UI cannot force `DELIVERED` without an actor. **Human gate:** Dhruv approves UX before any styling work.

## Phase 3 — Retrieval upgrade (ADAPTER)

- Chunk-level embedding index (per-tenant namespace, enforced at index build AND query).
- New eval: `IVS-01.1` (hosting regions) must flip from retrieval-miss abstention to cited answer, with zero regressions on T1–T6.

## Phase 4 — Real-world formats

- Multi-sheet workbooks, question-column autodetection, DOCX questionnaires.
- Every new format ships with its own T6-style structure-preservation test.

## Logs (append-only, Dhruv's convention)

- `DECISIONS.md` — every architectural choice, dated, with the alternative rejected.
- `GOTCHAS.md` — every surprise that cost >15 minutes.

## Explicitly out of scope until a paid pilot exists

Customer portal/SSO, multi-tenant self-service, OCR, browser portal automation, trust-center product. (Blueprint rule: sell first, automate second.)
