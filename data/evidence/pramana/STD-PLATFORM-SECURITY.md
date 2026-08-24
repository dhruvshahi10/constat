---
source_id: STD-PLATFORM-SECURITY
title: Platform Security Standard
type: standard
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: application security, access control, authentication, logging, rate limiting, secure development, vulnerability management, hosting
---

Output encoding. No value produced by the engine is ever assigned to innerHTML in any client. An answer is a paragraph lifted verbatim from an evidence document, and an evidence document is attacker-influenced input, so markup planted in an ingested file would otherwise execute in an operator's browser with access to every workspace on that console. Every network-derived value is set as text or appended as a text node. This was a real defect found during the 2026-08-24 self-review and fixed in both the public demo and the operator console.

Content Security Policy. The hosted site serves a policy with script-src set to self, so inline script cannot execute even if an output-encoding mistake is reintroduced. All client JavaScript is served as external files for this reason. The policy also sets frame-ancestors none, object-src none, base-uri none, and restricts connect-src to self. Strict-Transport-Security, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Cross-Origin-Opener-Policy and Permissions-Policy are set on every response.

Error handling. Serverless endpoints return an opaque error and a correlation reference; the exception type, message and any filesystem path go to the server log only. An error message can carry a path, a tenant name or a library internal, and echoing that to an anonymous caller would leak precisely what this product claims not to leak.

Request limits. Request bodies are capped before parsing. A question is capped at 600 characters. A best-effort per-instance rate limit of 20 requests per minute per client applies to both public endpoints; it is not a distributed limiter and is not represented as one.

Ingestion limits. Files above 64 MB are refused before being read, extracted text above 2 million characters is truncated with a visible marker, and text extraction is killed after 120 seconds. Ingestion consumes files supplied from outside the trust boundary and is bounded accordingly.

Network egress. In deterministic mode the engine makes no outbound network calls. With a live drafter enabled the only outbound destination is the selected model provider's API. The hosted site makes no third-party requests other than Google Fonts.

Dependencies. The engine depends on two third-party packages, openpyxl and pytest, both pinned. Everything else is Python standard library, which is a deliberate reduction of supply-chain surface rather than an aesthetic preference.

Secrets. API keys are read from a git-ignored environment file or the hosting platform's environment. No key is logged, committed, or included in any answer contract, run artifact or audit event.

Known gap, stated rather than discovered. There is no authentication on the operator console and no user accounts. The console binds to the loopback interface only and is a single-operator tool; anyone with access to the host has full access to every workspace on it, and a reviewer name is self-asserted. Authentication and role separation are required before Pramana is operated by more than one person or exposed beyond loopback. This is the most significant open item in the platform's own posture.
