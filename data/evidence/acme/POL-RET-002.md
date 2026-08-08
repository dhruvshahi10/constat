---
source_id: POL-RET-002
title: Backup and Archival Standard
type: standard
version: "1.1"
effective_date: 2025-06-20
expiry_date: 2026-06-20
owner: infra@acme.example
approval_status: approved
topics: backups, archival, data retention, customer data, recovery
assert.customer_data_deletion_days: 365
---
# Backup and Archival Standard

Production databases are backed up daily with point-in-time recovery. Encrypted backups are replicated to a secondary region.

Backup archives are retained on a 12-month rolling schedule. Customer content present in backup archives is purged as archives age out, meaning residual customer data may persist in encrypted archives for up to 365 days after termination.
