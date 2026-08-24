---
source_id: RPT-SELF-REVIEW-2026-08
title: Platform Self-Review Findings, August 2026
type: report
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: vulnerability management, application security, tenant isolation, prompt injection, penetration testing, secure development
assert.self_review_findings_fixed: 4
---

Scope. A security review of the Pramana platform itself, distinct from the evaluation of its answer gates, conducted on 2026-08-24 against the application, the hosted endpoints, the operator console and the ingestion path. Findings and fixes are published rather than summarised.

Finding 1, cross-tenant path traversal, fixed. A tenant name was used directly as a filesystem path component, so constructing a store with a name such as dot-dot-slash another-tenant loaded that tenant's documents while the store believed the crafted string was its own tenant. The retriever's boundary assertion then compared the crafted name against itself and passed. Isolation therefore depended on every caller validating the name, which is the failure mode the architecture explicitly claims to avoid. Tenant names are now validated against a strict pattern at both the store and the query boundary, the resolved directory must be a direct child of the evidence root, and a symbolic link leading out of a tenant directory is refused rather than followed.

Finding 2, stored cross-site scripting through evidence content, fixed. Answer text, gap text and provenance were assigned to innerHTML in both the public demo and the operator console. Because an answer is a paragraph copied verbatim from an evidence document, markup planted in a client-supplied PDF would have executed in the browser of whoever viewed the answer, with access to every workspace on that console. All client rendering now uses text nodes, all client script is served as external files, and the Content Security Policy forbids inline script so that a future mistake of the same kind cannot execute.

Finding 3, information disclosure through error responses, fixed. Unhandled exceptions returned the exception type and message to the caller, which could include filesystem paths and internal names. Errors now return an opaque message and a correlation reference, with detail written to the server log only.

Finding 4, unbounded public endpoints, fixed. Request bodies were read without a size cap and no rate limiting existed. Bodies are now capped before parsing and a per-instance limit of twenty requests per minute per client applies.

Audit log property, clarified rather than fixed. The hash chain proves no event was edited. It does not, on its own, prove no log was replaced wholesale, because anyone able to write the file can recompute a consistent chain. Optional HMAC signing was added so a signed deployment rejects a regenerated log; when signing is not enabled the log is tamper-evident rather than tamper-resistant, and the system reports which property is in force instead of implying the stronger one.

Reviewer identity, corroborated rather than authenticated. A reviewer name remains self-asserted. Each decision now records the operating system user and host alongside the claimed name, inside the signed hash-chained event, and explicitly records that the actor was not authenticated. This is corroboration, and is not represented as authentication.

Open items. There is no authentication and no role separation on the operator console; it binds to loopback and is a single-operator tool. No independent penetration test has been performed. Both are open and are stated here rather than left for a reviewer to discover.

Regression coverage. Each finding above has a corresponding test in the platform security suite, and every one of those tests failed before its fix.
