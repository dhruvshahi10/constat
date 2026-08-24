---
source_id: STD-TENANT-ISOLATION
title: Tenant Isolation Architecture Standard
type: standard
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: tenant isolation, access control, multi-tenancy, data leakage, encryption
---

Isolation is structural, not filtered. Each tenant's evidence is a separate directory, and an evidence store is constructed from exactly one tenant directory. There is no code path that loads two tenants into one store, and therefore no query that could return the wrong tenant's document by omitting a filter. This is a deliberate rejection of the row-level-filter pattern, where isolation depends on every query remembering a WHERE clause.

Boundary assertion. Every chunk carries the tenant it came from. The retriever raises PermissionError when the requesting tenant does not match the store's tenant, and asserts tenant identity on each chunk before returning it. A mismatch fails loudly rather than degrading to an empty or partial result.

Adversarial verification. The eval suite includes a decoy tenant whose documents are deliberately similar in wording to the primary tenant's, so that a lexical or semantic match would surface them if isolation depended on relevance scoring. The tests assert zero cross-tenant chunks retrieved, and assert that a mismatched tenant request raises rather than returns. These tests run on every change and a failure blocks release.

Isolation of unapproved material. Documents staged during onboarding are written to a subdirectory that the evidence store does not read, so material awaiting human approval is invisible to retrieval by construction rather than by a status filter.
