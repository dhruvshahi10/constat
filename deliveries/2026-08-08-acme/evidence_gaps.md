# Evidence gaps — Acme

Engagement date: 2026-08-08  
Prepared by Pramana from run `20260825-190905-acme-mock`

17 of 24 questions were answered from approved evidence and cited. 7 were refused: the engine had nothing it was allowed to cite, so it wrote nothing.

This file is the list of what has to exist before those questions can be answered from evidence. Each item names the document to produce, renew or reconcile and who it was routed to. Nothing here requires Pramana to fix — it requires a document.

## Summary

| Reason | Questions |
| --- | ---: |
| Two approved documents disagree | 2 |
| The supporting document has expired | 2 |
| Certification claimed, no certificate on file | 1 |
| No approved document covers this | 1 |
| Needs legal, not evidence | 1 |
| **Total open items** | **7** |

## Two approved documents disagree — 2 questions

Both are approved and in force, and they say different things about the same machine-checked value. Until they agree, neither can be cited — publishing either one would contradict a document your own company also stands behind.

### DSP-01.1 · Data Security & Privacy

**Question asked:** Within how many days of contract termination is customer data deleted from your systems, including backups?

- **What has to happen:** Decide which value is correct, correct and re-approve the document that is wrong, so POL-RET-001 agree. Both are approved today, which is why neither can be cited.
- **Document(s):**
    - POL-RET-001 — Data Retention and Deletion Policy (v2.0, owner privacy@acme.example)
    - POL-RET-002 — Backup and Archival Standard (v1.1, owner infra@acme.example), expired 2026-06-20 — also out of date
- **Routed to:** The owners of the conflicting documents — infra@acme.example, privacy@acme.example
- **What the control recorded:** POL-RET-001: conflicting approved sources on a machine-checked assertion — route to owners for reconciliation

### PRV-01.1 · Privacy

**Question asked:** Do you support verified deletion (certificate of deletion) on customer request?

- **What has to happen:** Decide which value is correct, correct and re-approve the document that is wrong, so POL-RET-001 agree. Both are approved today, which is why neither can be cited.
- **Document(s):**
    - POL-RET-001 — Data Retention and Deletion Policy (v2.0, owner privacy@acme.example)
- **Routed to:** The owners of the conflicting documents — infra@acme.example, privacy@acme.example
- **What the control recorded:** POL-RET-001: conflicting approved sources on a machine-checked assertion — route to owners for reconciliation

## The supporting document has expired — 2 questions

The document exists and was approved, but its own expiry date has passed. An expired document cannot support a present-tense claim about how you operate today.

### AIS-01.1 · Application Security

**Question asked:** Has an independent penetration test of the application been performed in the last 12 months? Summarize scope and outcome.

- **What has to happen:** Re-run or re-issue the underlying work, then approve the new version of RPT-PEN-2024 into the corpus. Extending a date on an expired document without redoing the work would make the claim false rather than stale.
- **Document(s):**
    - RPT-PEN-2024 — External Penetration Test Report (Redwood Security) (v1.0, owner security@acme.example), expired 2025-06-10
- **Routed to:** Your subject-matter expert for Application Security
- **What the control recorded:** RPT-PEN-2024 v1.0: EXPIRED 2025-06-10 — cannot support a current-state claim; route to security@acme.example

### IVS-01.1 · Infrastructure

**Question asked:** Where is customer data hosted (provider and regions)?

- **What has to happen:** Re-run or re-issue the underlying work, then approve the new version of POL-RET-002 into the corpus. Extending a date on an expired document without redoing the work would make the claim false rather than stale.
- **Document(s):**
    - POL-RET-002 — Backup and Archival Standard (v1.1, owner infra@acme.example), expired 2026-06-20
- **Routed to:** Your subject-matter expert for Infrastructure
- **What the control recorded:** POL-RET-002 v1.1: EXPIRED 2026-06-20 — cannot support a current-state claim; route to infra@acme.example

## Certification claimed, no certificate on file — 1 question

The question asks whether you hold a certification. Nothing of certificate or attestation class was found, and certification is never inferred from a policy, a plan or a roadmap that mentions the same scheme.

### A&A-02.1 · Audit & Assurance

**Question asked:** Is your organization ISO/IEC 27001 certified? Provide certificate number and expiry.

- **What has to happen:** Supply the certificate or attestation report itself — the signed auditor deliverable, with its scope and validity dates. If the certification is not yet held, the honest answer to this question is the roadmap, given by a person, not by the engine.
- **Document(s):** none on file — this is the gap.
- **Routed to:** Your subject-matter expert for Audit & Assurance
- **What the control recorded:** Retrieval found no sufficiently relevant approved evidence.

## No approved document covers this — 1 question

Nothing in your approved corpus addresses the question, so no answer was written. This is the largest and most fixable group: each one is a document that does not exist yet, or exists but has never been approved into the corpus.

### STA-01.1 · Supply Chain

**Question asked:** Do you assess the security posture of critical third parties/subprocessors?

- **What has to happen:** Produce an approved document covering Supply Chain that answers this question, and add it to Acme's corpus. Nothing approved today addresses it, so no answer was written.
- **Document(s):** none on file — this is the gap.
- **Routed to:** Your subject-matter expert for Supply Chain
- **What the control recorded:** Retrieval found no sufficiently relevant approved evidence.

## Needs legal, not evidence — 1 question

The question asks for a contractual or liability commitment. That is a decision counsel makes, not a fact evidence can establish, so it was routed before any answer was drafted.

### LGL-01.1 · Customer Legal Addendum

**Question asked:** Will Vendor contractually commit to unlimited liability for any security breach and guarantee a 99.99% uptime SLA with financial penalties?

- **What has to happen:** Counsel answers this in the contract, not the questionnaire. Nothing was drafted, and nothing should be answered from evidence.
- **Document(s):** none on file — this is the gap.
- **Routed to:** Your legal / contracts owner
- **What the control recorded:** Question requests a contractual/legal commitment; outside answerable scope.

## Answered, with a note on file

These were answered and cited — they are not refusals and are not counted above. Each one released an answer while rejecting something alongside it, so closing the note makes an answer that already ships a stronger one.

- **CEK-01.1** · Cryptography — POL-RET-002 v1.1: EXPIRED 2026-06-20 — cannot support a current-state claim; route to infra@acme.example
- **CEK-02.1** · Cryptography — POL-RET-002 v1.1: EXPIRED 2026-06-20 — cannot support a current-state claim; route to infra@acme.example

---

Every refusal above is recorded in the audit log shipped with this package, with the gate that made it and the timestamp. A refusal is not a missing answer — it is the system declining to make a claim it cannot support.
