---
source_id: POL-AIGOV-001
title: AI Governance Policy
type: policy
version: "1.0"
effective_date: 2026-08-25
expiry_date: 2027-08-25
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: ai governance, model governance, risk management, human review, logging, machine learning, llm, iso 42001, oversight
---
# AI Governance Policy

Purpose and intended use. Constat is an AI-assisted system that drafts and refuses answers to customer security questionnaires from a governed evidence corpus. It is not a decision-making system, it does not act autonomously, and its outputs are proposals subject to deterministic validation and human accountability.

Governing principle. The model is treated as an untrusted component. Every property that matters to correctness or safety is enforced outside the model, in code that runs after it: the citation requirement, source approval status, source validity dates, contradiction quarantine, certification evidence class, workspace isolation and legal-scope routing. Changing model or provider changes fluency and cost; it does not change what the system is permitted to publish.

Fail-closed by design. Absence of evidence produces refusal, not a hedged answer. Stale, contradicted or unapproved evidence produces refusal. A drafter that is unavailable, or that returns output which does not parse as the answer contract, produces refusal. Every refusal names the specific gap and the human or function it is routed to.

Accountability and logging. Every state transition and every human decision is written to an append-only, hash-chained log that names the actor. The drafter identity, model version and prompt version are recorded on every answer contract, so any published answer can be traced to the model and the evidence that produced it.

Change control. The evaluation suite that defines these invariants is treated as fixed: feature work may not modify it. A change that would alter a safety invariant must be argued against the suite rather than around it.
