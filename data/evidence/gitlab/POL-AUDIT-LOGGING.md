---
source_id: POL-AUDIT-LOGGING
title: Audit Logging Policy
type: policy
version: "1.0"
effective_date: 2026-07-26
expiry_date: 2027-07-26
owner: security@gitlab.com
approval_status: approved
topics: logging, audit trail, monitoring
---

In line with GitLab’s regulatory obligations, changes to 
 controlled documents must be approved or merged by a code owner. All contributions are welcome and encouraged.

To ensure the proper operation and security of GitLab.com, GitLab logs critical information system activity.

The audit logging policy applies to all systems within our production environment. The production environment includes all endpoints and cloud assets used in hosting GitLab.com and its subdomains. This may include third-party systems that support the business of GitLab.com.

GitLab Team Members 
 Responsible for following the requirements in this policy

Security Team 
 Responsible for implementing and executing this policy

System Owners 
 Definition of individual audit log criteria; Definition and execution of system audit log procedures

Security Management (Code Owners) 
 Responsible for approving significant changes and exceptions to this policy

- GitLab shall log and monitor critical information system activity.

- Logs must be retained for a defined period of time.

- Logs must not be modified and or deleted.

- Access to audit log data must be limited based on the principle of least privilege.

Inline with GitLab’s Continuous Monitoring Controls
System Owners are responsible for determining what constitutes “critical information system activity” in their respective system based on their experience and professional judgement

Such activity is then documented either in the handbook or a runbook, whichever is found to be appropriate.

Audit logging process must be created and implemented by the department(s) or team(s) responsible for a given system.

Exceptions to this policy will be tracked as per the Information Security Policy Exception Management Process .
