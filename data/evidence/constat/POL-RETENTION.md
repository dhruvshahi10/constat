---
source_id: POL-RET-001
title: Data Retention and Deletion Policy
type: policy
version: "1.0"
effective_date: 2026-08-25
expiry_date: 2027-08-25
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: data retention, deletion, privacy, personal data, logging, backups, disposal
---
# Data Retention and Deletion Policy

Uploaded documents are hard deleted from the workspace fourteen days after upload. Deletion removes the stored file, not merely a database reference to it.

Run artifacts — the completed workbook, the answer contracts and the audit log for a run — are retained for the life of the workspace and are deleted with it on request.

Audit logs are append-only and hash-chained by design, so entries are never edited or selectively removed. An audit log is retained as a whole file or deleted as a whole file. This is a deliberate trade-off in favour of tamper evidence over selective erasure.

Personal data. The platform stores the email address used to create a workspace and the hash of that workspace's access token. It stores no other personal data, no payment details and no behavioural profile.

Deletion on request. A request from the workspace owner results in deletion of the workspace, its documents, its run artifacts and its token record.
