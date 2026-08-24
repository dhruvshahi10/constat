---
source_id: PLN-INCIDENT-RESPONSE
title: Northwind Health — Incident Response Plan
type: plan
version: 1.4
effective_date: 2025-11-20
expiry_date: 2026-11-20
owner: soc@northwind.example
approval_status: approved
topics: incident response, business continuity, vulnerability management
assert.breach_notification_hours: 72
assert.rto_hours: 4
assert.rpo_hours: 1
assert.critical_vuln_remediation_days: 7
ingested_from: Incident Response Plan.pdf
ingested_at: 2026-08-24
inferred_fields: assertions (breach_notification_hours, rto_hours, rpo_hours, critical_vuln_remediation_days)
approved_by: Priya Nair <priya.nair@northwind.example>
---

Northwind Health — Incident Response Plan
Version 1.4
Approved: 2025-11-20
Valid until: 2026-11-20
Owner: soc@northwind.example

Northwind notifies affected customers within 72 hours of confirming a personal d
ata breach. The incident response plan is tested at least annually through a tab
letop exercise; the most recent exercise was conducted on 2026-02-11.

RTO for production services is 4 hours. RPO is 1 hours.

Critical vulnerabilities are remediated within 7 days of confirmation; high seve
rity within 30 days.
