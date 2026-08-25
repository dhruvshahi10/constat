---
source_id: STD-MODEL-001
title: Model and Data Access Boundary Standard
type: standard
version: "1.0"
effective_date: 2026-08-25
expiry_date: 2027-08-25
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: ai governance, model access, data access, boundaries, llm, prompt, retrieval, egress
---
# Model and Data Access Boundary Standard

Scope of model access. The model receives exactly three things: the text of one question, at most four retrieved excerpts from one workspace's approved evidence, and a fixed system contract. It receives no filesystem access, no network access, no database credentials, no tool or function-calling surface, and no ability to invoke another model. The drafter is a pure text-in, JSON-out component.

Retrieved excerpts are bounded and workspace-scoped. The retriever draws only from a store constructed for a single workspace and asserts workspace identity on every chunk before returning it. A model cannot be shown another customer's document even if a prompt asks for one, because no code path assembles such a prompt.

Model output is not trusted. The drafter returns a proposed answer and proposed citations. Every citation is then re-checked in code against the evidence store: unknown source identifiers are rejected, unapproved sources are rejected, expired sources are rejected, contradicted sources are rejected, and certification claims are rejected unless supported by a source of certificate or attestation class. An answer with no surviving citation is discarded and the question is refused. No wording of model output can cause an uncited claim to be published.

Retrieval. Retrieval is semantic where the embedding model is available and falls back to lexical n-gram matching where it is not. Both paths are subject to identical gates; retrieval quality affects coverage, never permissibility.

Egress. The only outbound destination during a run is the selected model provider's API endpoint.
