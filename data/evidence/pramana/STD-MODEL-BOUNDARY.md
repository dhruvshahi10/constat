---
source_id: STD-MODEL-BOUNDARY
title: Model and Data Access Boundary Standard
type: standard
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: ai governance, model access, data access, encryption, subprocessors
---

Scope of model access. A language model in Pramana receives exactly three things: the text of one question, retrieved excerpts from one tenant's approved evidence, and a fixed system contract. It receives no filesystem access, no network access, no database credentials, no tool or function-calling surface, and no ability to invoke another model. The drafter is a pure text-in, JSON-out component.

Retrieved excerpts are bounded. The retriever returns at most four chunks, drawn from a store constructed for a single tenant, and asserts tenant identity on every chunk before returning it. A model therefore cannot be shown another customer's document even if a prompt asks it to, because no code path assembles such a prompt.

Model output is not trusted. The drafter returns a proposed answer and proposed citations. Every citation is then re-checked in code against the evidence store: unknown source ids are rejected, unapproved sources are rejected, expired sources are rejected, contradicted sources are rejected, and certification claims are rejected unless supported by a source typed certificate or attestation. An answer with no surviving citation is discarded and the question is refused. A model cannot cause an uncited claim to be published by any wording of its output.

Model failure is treated as refusal. If the drafter returns output that does not parse as the answer contract, or the model endpoint is unavailable, the question abstains and is routed to a human. There is no fallback path that produces an answer without evidence.

Hosted demo. The public demo at pramana-red.vercel.app runs the deterministic drafter only. Text entered into the public demo is not sent to any third-party model provider. It is processed in a serverless function, used to retrieve from a synthetic corpus, and is not persisted.
