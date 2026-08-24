---
source_id: LST-SUBPROCESSORS
title: Subprocessor and Hosting Register
type: register
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: subprocessors, third parties, hosting, supply chain, privacy
---

Hosting. The public site and its two serverless functions are hosted on Vercel. Vercel processes request metadata and serves static content. No customer evidence corpus is hosted there; the only corpora deployed with the site are synthetic demonstration data.

Early-access records. Email addresses submitted through the early-access form are stored in Supabase. No other personal data is collected by the site.

Source control. The source code is public on GitHub.

Model providers, optional and operator-selected. Anthropic and Google are supported as live drafters. Neither is used by any hosted Pramana surface; both are enabled only by an operator running the engine themselves, per run, with an explicit flag.

Operator-run deployments. In an operator-run deployment the evidence corpus, run artifacts and audit logs stay on the operator's own infrastructure. Pramana adds no subprocessor to that deployment beyond a live model provider if the operator chooses to enable one.
