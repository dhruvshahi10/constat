---
source_id: STD-ENC-001
title: Encryption Standard
type: standard
version: "1.4"
effective_date: 2025-12-05
expiry_date: 2026-12-05
owner: security@acme.example
approval_status: approved
topics: encryption, tls, at rest, in transit, key management, kms, aes
---
# Encryption Standard

Data in transit is protected with TLS 1.2 or higher on all external and inter-service connections; weak ciphers are disabled. Data at rest is encrypted with AES-256 across databases, object storage and backups.

Encryption keys are managed in a cloud KMS with annual rotation, split administrative duties and audit logging of key usage.
