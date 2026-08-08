# DECISIONS.md (append-only)

- 2026-08-08 — Gates enforced in code, not prompt. Rejected: prompt-only guardrails (unauditable, drafter-dependent). Consequence: MockDrafter and AnthropicDrafter share identical safety posture.
- 2026-08-08 — Contradiction detection via declared frontmatter assertions (`assert.<key>`). Rejected for v0: NLI/semantic contradiction (non-deterministic, untestable as a hard gate).
- 2026-08-08 — Lexical retrieval for v0. Rejected: embeddings-first (opaque scoring; retrieval misses must fail closed anyway, and one deliberate miss (IVS-01.1) is kept in the demo as proof).
- 2026-08-08 — Cert-class claims require source type certificate/attestation even when a truthful "no" exists. Rationale: negative certification answers have deal consequences; phrasing belongs to a human (blueprint p.12).
- 2026-08-08 — Audit log = hash-chained JSONL over SQLite/DB. Rationale: tamper-evidence demoable in one pytest; DB adds nothing at this scale.
- 2026-08-08 — Demo auto-approval only for gate-clean complete-coverage drafts, explicitly labeled SIMULATED in log + report. Rejected: silent auto-approval (misrepresents the human-gate design).
- 2026-08-08 — Default live drafter = Haiku 4.5; gates make the cheap model safe. TRUSTOPS_MODEL env overrides.
