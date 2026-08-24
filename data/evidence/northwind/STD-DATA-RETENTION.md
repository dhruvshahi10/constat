---
source_id: STD-DATA-RETENTION
title: Northwind Health — Data Retention and Deletion Standard
type: standard
version: 2.0
effective_date: 2026-03-01
expiry_date: 2027-03-01
owner: dpo@northwind.example
approval_status: approved
topics: encryption, data retention, logging
assert.customer_data_deletion_days: 30
ingested_from: Data Retention and Deletion Standard.docx
ingested_at: 2026-08-24
inferred_fields: type — POSSIBLE CERTIFICATE/ATTESTATION, typed as 'standard' pending human confirmation, assertions (customer_data_deletion_days)
approved_by: Priya Nair <priya.nair@northwind.example>
---

Northwind Health — Data Retention and Deletion Standard

Version 2.0

Effective: 2026-03-01

Review Date: 2027-03-01

Owner: dpo@northwind.example

Customer data is deleted within 30 days of contract termination, including all backup copies. Deletion is verified by the Data Protection Officer and a certificate of deletion is issued on request.

Operational logs are retained for 400 days. Security telemetry is retained for 13 months in the SIEM.

Encryption at rest uses AES-256. Keys are managed in AWS KMS with annual rotation.
