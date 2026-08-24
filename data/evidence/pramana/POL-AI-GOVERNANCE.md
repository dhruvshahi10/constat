---
source_id: POL-AI-GOVERNANCE
title: AI Governance Policy
type: policy
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: ai governance, model governance, risk management, human review, logging, iso 42001
---

Purpose and intended use. Pramana is an AI-assisted system for drafting and refusing answers to customer security questionnaires from a governed evidence corpus. It is not a decision-making system, it does not act autonomously, and its outputs are proposals subject to deterministic validation and human accountability.

Governing principle. The model is treated as an untrusted component. Every property that matters to correctness or safety is enforced outside the model, in code that runs after it: citation requirement, source approval, source validity dates, contradiction quarantine, certification evidence class, tenant isolation and legal-scope routing. Changing model or provider changes fluency and cost; it does not change what the system is permitted to publish.

Fail-closed by design. Absence of evidence produces refusal, not a hedged answer. Stale, contradicted or unapproved evidence produces refusal. Drafter unavailability or malformed drafter output produces refusal. Every refusal names the specific gap and the human or function it is routed to.

Measured behaviour. The system's safety properties are asserted by an adversarial evaluation suite that runs on every change, including certification inference, evidence staleness, source contradiction, legal-commitment scope, cross-tenant retrieval, prompt injection and audit-log tampering. A failure blocks release. The release gate is that the count of unsupported material claims is zero.

Accountability and logging. Every state transition, every gate decision and every human decision is written to an append-only, hash-chained log that names the actor. The drafter identity, model version and prompt version are recorded on every answer contract, so any published answer can be traced to the model and evidence that produced it.

Change control. The evaluation suite defining these invariants is treated as fixed: feature work may not modify it. A change that would alter a safety invariant must be argued against the suite, not around it.
