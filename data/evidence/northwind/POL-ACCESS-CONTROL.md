---
source_id: POL-ACCESS-CONTROL
title: Northwind Health — Access Control Policy
type: policy
version: 3.1
effective_date: 2026-01-15
expiry_date: 2027-01-15
owner: priya.nair@northwind.example
approval_status: approved
topics: access control, authentication
assert.access_review_days: 90
ingested_from: Access Control Policy v3.1.pdf
ingested_at: 2026-08-24
inferred_fields: assertions (access_review_days)
approved_by: Priya Nair <priya.nair@northwind.example>
---

Northwind Health — Access Control Policy
Version 3.1
Effective Date: 2026-01-15
Next Review: 2027-01-15
Owner: priya.nair@northwind.example

1. Purpose
This policy governs how workforce access to Northwind production and corporate s
ystems is granted, reviewed and revoked.

2. Multi-factor authentication
Multi-factor authentication is enforced for all workforce access to production e
nvironments, the corporate identity provider, and all administrative consoles. N
o exceptions are granted without a documented risk acceptance approved by the CI
SO.

3. Access reviews
Access rights are reviewed every 90 days by the system owner. Access is revoked
within 24 hours of termination, and privileged access is revoked immediately upo
n notice.

4. Least privilege
Role-based access control is applied to all production systems. Standing product
ion access is prohibited; engineers request time-bound elevation through the acc
ess broker.
