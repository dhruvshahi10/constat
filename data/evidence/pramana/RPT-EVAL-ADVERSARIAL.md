---
source_id: RPT-EVAL-ADVERSARIAL
title: Adversarial Evaluation Report
type: report
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: accuracy, evaluation, testing, ai governance, prompt injection, model governance
assert.adversarial_prompts: 59
assert.correctly_refused_pct: 95.5
assert.released_without_citation: 0
---

Scope and method. Pramana is evaluated against 59 adversarial prompts spanning certification inference, stale evidence, source contradiction, legal-commitment scope, out-of-corpus questions, prompt injection delivered through the question, prompt injection planted inside an approved evidence document, cross-tenant attribution, false premises, and positive controls that the corpus genuinely supports. Every prompt was labelled with the required outcome before the harness was first run, and labels are not revised to match observed behaviour.

Headline results as at 2026-08-24, using the deterministic drafter. Of 44 prompts where releasing any answer would be wrong, 42 were correctly refused, or 95.5 percent. Of 15 prompts the corpus genuinely supports, 12 were answered with a surviving citation, or 80.0 percent. Overall 91.5 percent of prompts produced the labelled outcome.

The release gate. 0 answers were released without a surviving citation. This is the invariant the engine enforces on every run and it is asserted by the test suite: an answer with no citation that survived the gates is discarded rather than published.

Known failures, published rather than summarised. 2 prompts released an answer where the label required refusal; in each case the released answer carried a valid citation, and the failure was one of question scoping rather than a fabricated claim. Retrieval is lexical, and a number of positive controls were refused because retrieval did not surface a sufficiently strong match in a document that does contain the answer. Those refusals are fail-closed and are counted as failures rather than excused.

Reproduction. The prompt set, the harness and the full per-prompt results are published in the repository, and the harness can be re-run against any supported drafter.
