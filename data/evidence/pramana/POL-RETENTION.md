---
source_id: POL-RETENTION
title: Data Retention and Deletion Policy
type: policy
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: data retention, deletion, privacy, personal data, logging
---

Hosted site. The only data the public site retains is an email address and an optional note voluntarily submitted through the early-access form. These are deleted within 30 days of a request to the owner. Questions typed into the public demo are processed in memory and are not written to any store.

Operator-run deployments. Evidence corpora, run artifacts, delivered workbooks and audit logs are written to the operator's own filesystem and are under the operator's control and retention schedule. Pramana does not copy them anywhere and has no remote store.

Audit logs. Audit logs are append-only and hash-chained by design, so entries are not edited or selectively removed; an audit log is deleted as a whole file or retained as a whole file. This is a deliberate trade-off in favour of tamper evidence.

Deletion on request. A request to the owner results in deletion of the requester's early-access record within 30 days. Because no customer evidence is held on hosted infrastructure, there is no customer content to delete beyond that record.
