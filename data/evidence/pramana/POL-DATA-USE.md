---
source_id: POL-DATA-USE
title: Customer Data Use and Model Training Policy
type: policy
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: ai governance, training, privacy, data retention, subprocessors, personal data
---

No training on customer content. Pramana does not train, fine-tune, or adapt any model on customer evidence, customer questionnaires, or customer answers. The system has no training pipeline. Retrieval is lexical and computed at query time from the tenant's files; there is no embedding index and no learned artifact derived from customer content.

Third-party model providers. When an operator enables a live drafter, retrieved excerpts and the question are sent to that provider's API for the duration of the request. Two providers are supported: Anthropic and Google. Provider data-use terms differ by plan, and this is the material distinction an evaluator should note: Google's free Gemini tier permits Google to use submitted content to improve its products, whereas paid API tiers of both providers do not train on submitted content.

Consequence of the above. Because free-tier terms permit provider-side use of inputs, Pramana's own hosted surfaces never use a free-tier live model on visitor or customer input. The hosted demo is deterministic. An operator running Pramana locally selects the drafter explicitly per run, and the selected drafter and model version are recorded in the run's audit log and in every answer contract.

Local processing. In an operator-run deployment, the evidence corpus, run artifacts, exported workbooks and audit logs remain on the operator's own machine or infrastructure. Pramana has no telemetry, no analytics, and transmits no usage data.

Retention on hosted surfaces. The public site persists exactly one category of personal data: an email address, and an optional free-text note, submitted voluntarily through the early-access form. Nothing else entered on the site is stored.
