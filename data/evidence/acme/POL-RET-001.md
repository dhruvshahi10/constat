---
source_id: POL-RET-001
title: Data Retention and Deletion Policy
type: policy
version: "2.0"
effective_date: 2025-11-01
expiry_date: 2026-11-01
owner: privacy@acme.example
approval_status: approved
topics: data retention, deletion, customer data, disposal
assert.customer_data_deletion_days: 90
---
# Data Retention and Deletion Policy

Customer content is retained only for the duration of the subscription. Upon contract termination, all customer content is deleted from production systems within 90 days, followed by certificate of deletion on request.

Deletion covers primary datastores and object storage. Media sanitization follows NIST SP 800-88 guidelines.
