---
name: claim-author
description: Turn a policy excerpt, a Vanta test, or an answered question into a Constat claim JSON with a person as owner, scope, exceptions, evidence refs, audience and validity. Use when asked to "author a claim", "turn this into a claim", "add a claim for X".
---

# Claim author

Produce one JSON object matching `constat/claims/models.py` (`Claim.from_dict`). Rules, in order:

1. **One fact per claim.** If the source states two things, make two claims.
2. **Owner is a person's address**, never a team alias. If the source names a team, ask who; do not guess.
3. **Exceptions are a list**, each a complete sentence a customer must see. "No customer data is used for training" with telemetry retained is two sentences: the statement and the exception. The completeness gate checks each exception's words appear in any answer.
4. **Scope** says what the statement covers (systems, data classes, regions). Blank scope is refused by the store.
5. **Evidence refs**: `vanta_test` with `vanta:test:<id>` where a test exists; otherwise `policy`, `standard`, `report`, `certificate`, `attestation`, `config` or `statement` with the document id and version. A certification claim needs `certificate` or `attestation` evidence or it will be held for a human.
6. **Audience**: `public` only if it may appear on the trust centre verbatim; `nda` by default; `internal` for anything naming architecture, vendors or findings.
7. **Validity**: `valid_until` is the next review date of the source document, never more than a year out.
8. **Status** is `draft`. A second person approves it into `verified` (`POST /v1/claims/propose`, then approve).
9. **Keywords and topics**: the words a questionnaire would use, including synonyms (`mfa`, `multi-factor`, `2fa`).
10. No numbers in the statement that the evidence does not state.
11. **Product context**: `products` (`catalog`, `ai-features`, `mcp`), `data_classes` (`metadata`, `customer-data`, `prompts`) and `deployment` (`saas-multi-tenant`, `saas-single-tenant`, `self-hosted`, `hybrid`), from `constat/claims/scope.py`. Declare every product and data class the fact is true for and no others: a question naming a product or data class the claim does not cover is held with `PRODUCT_SCOPE_MISMATCH`.

Output the JSON, then one line naming what you were unsure about.

For a whole document, `POST /v1/claims/author` (or `constat.claims.author.author_document`) drafts one claim per fact with the quoted span as evidence and opens them as proposals; review each against these rules before a second person approves.
