---
source_id: STD-ISO-001
title: Workspace Isolation Architecture Standard
type: standard
version: "1.0"
effective_date: 2026-08-25
expiry_date: 2027-08-25
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: tenant isolation, multi-tenancy, data leakage, segregation, workspace, access control, cross-tenant
---
# Workspace Isolation Architecture Standard

Isolation is structural rather than filtered. Each workspace's evidence is a separate directory, and an evidence store is constructed from exactly one workspace directory. There is no code path that loads two workspaces into a single store, so there is no query that can return the wrong customer's document by omitting a condition. This is a deliberate rejection of the row-level-filter pattern, where correctness depends on every query remembering a clause.

Every retrieved chunk carries the workspace it came from. The retriever refuses a request whose workspace does not match the store it was built from, and asserts workspace identity on each chunk before returning it. A mismatch fails loudly rather than degrading to an empty or partial result.

Workspace names are validated before they are used as a filesystem path, and the resolved directory must be a direct child of the evidence root. A symbolic link that leads out of a workspace directory is refused rather than followed.

Access control and isolation are separate controls and are tested separately. The bearer token establishes which workspace a caller may address; the store construction establishes that a workspace can only ever see its own documents. Neither is relied upon to do the other's job.

Adversarial verification. The evaluation suite contains a decoy workspace whose documents are deliberately worded to resemble the primary workspace's, so that isolation depending on relevance scoring would surface them. The tests assert zero cross-workspace chunks retrieved and assert that a mismatched request raises. A failure blocks release.
