---
source_id: STD-PLAT-001
title: Platform Security Standard
type: standard
version: "1.0"
effective_date: 2026-08-25
expiry_date: 2027-08-25
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: application security, secure development, vulnerability management, uploads, rate limiting, headers, availability, penetration testing
---
# Platform Security Standard

Output encoding. No value produced by the engine is inserted into a page as markup. An answer is a paragraph lifted verbatim from an uploaded document, and an uploaded document is attacker-influenced input, so markup planted in a file would otherwise execute in the browser of whoever reviews the answer. Engine output is set as text.

Upload handling. Uploads are bounded in size before they are read, extraction is bounded in time and in extracted length, and only a fixed set of file types is accepted. Text extraction runs in-process with no shell invocation.

Transport and headers. The hosted application is served over TLS with strict transport security, content type sniffing disabled, framing denied, and a content security policy that forbids inline script.

Request limits. Request bodies are capped before parsing and public endpoints are rate limited per client.

Error handling. Errors returned to a caller are opaque and carry a correlation reference; exception detail, including any filesystem path, is written to the server log only.

Secrets. Provider API keys are held in the platform environment or supplied per workspace by the customer. No key is logged, committed to source control, or included in any answer contract, run artifact or audit event. Access tokens are stored only as SHA-256 digests.

Availability posture, stated rather than implied. The application runs as a single instance because the run queue and the local database are single-process components. There is no high-availability configuration, no automatic failover and no uptime commitment. Scaling beyond one instance requires the changes recorded in the project backlog and has not been done.

Known gaps. No independent penetration test has been performed. Workspace identifiers are derived from the organisation name and are therefore guessable, which discloses that a workspace exists to anyone who guesses it; access still requires a valid token bound to that workspace. Scanned image PDFs cannot be read without optical character recognition, which is not implemented, so such documents are rejected rather than silently partially ingested.
