---
source_id: POL-SDLC-001
title: Secure Development Policy
type: policy
version: "1.2"
effective_date: 2026-01-25
expiry_date: 2027-01-25
owner: engineering@acme.example
approval_status: approved
topics: secure development, sdlc, code review, sast, dependency scanning, ci/cd, vulnerability management, patching
---
# Secure Development Policy

All production code changes require peer review and passing CI, including static application security testing (SAST) and dependency vulnerability scanning, before merge. Critical and high vulnerabilities are remediated within 15 and 30 days respectively.

Infrastructure is managed as code with change control. Production deployments are gated and auditable.
