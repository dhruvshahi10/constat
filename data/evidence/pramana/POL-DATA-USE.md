---
source_id: POL-DATA-001
title: Customer Data Use and Model Training Policy
type: policy
version: "1.0"
effective_date: 2026-08-25
expiry_date: 2027-08-25
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: ai governance, training, model training, privacy, personal data, subprocessors, data use, confidentiality
---
# Customer Data Use and Model Training Policy

No training on customer content. Pramana operates no training pipeline. No model is trained, fine-tuned or adapted on customer evidence, customer questionnaires or customer answers, and no learned artifact is derived from customer content.

What crosses the boundary. When an answer is drafted, exactly one question and at most four retrieved excerpts are sent to the model provider. A whole document is never transmitted. Documents themselves remain in the customer's workspace.

Three key modes, with different guarantees, stated plainly because they are not equivalent. In demo mode the platform's own free-tier key is used and only public evidence may be uploaded, because free-tier terms permit the provider to use submitted content to improve their services; a published SOC 2 report loses nothing by that, and confidential runbooks would. In bring-your-own-key mode the customer supplies their own provider key, so the terms that apply are the customer's own contract with that provider. In managed mode a paid key is used under a no-training commitment, and retention, residency and that commitment become contract terms rather than marketing claims.

Deletion. Uploaded documents are hard deleted from the workspace fourteen days after upload. Deletion removes the file, not merely a reference to it.

Telemetry. The platform sends no usage analytics and no product telemetry to any third party.
