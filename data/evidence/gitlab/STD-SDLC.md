---
source_id: STD-SDLC
title: Software Development Lifecycle Standard
type: standard
version: "1.0"
effective_date: 2026-02-12
expiry_date: 2027-02-12
owner: security@gitlab.com
approval_status: approved
topics: sdlc, testing, release
---

In line with GitLab’s regulatory obligations, changes to 
 controlled documents must be approved or merged by a code owner. All contributions are welcome and encouraged.

Secure software development is critical to developing and maintaining a safe and trusted application. This standard outlines the general components of GitLab’s software development lifecycle.

This standard applies to anyone developing code at GitLab in support of GitLab’s production applications. For in depth view of development process, see product development flow .

Security Governance 
 Responsible for creating and implementing this standard

Team members 
 Responsible for execution of the standard statements

This stage occurs across different mediums depending upon each team’s individual processes.

During this stage, the following information is established:

- a detailed project plan with milestones and deliverables is created in coordination with relevant stakeholders

- what the application or functionality will do

- the resources required to complete the project

Identified requirements are documented in the project management tool and made available for review and approval by relevant stakeholders.

During the design stage, design documents are captured in the project management tool as version controlled documents.

- Architecture: Teams define if they want a specific type of template or if they want to implement any type of industry practice.

- User Interface: Teams define the way users will be interacting with the application or function.

- Security: Developers must define how they will keep the application secure. This includes deciding how to protect user data and general application data.

- Programming: Define the project’s tech and tool stacks.

- Components: Define the components that will be needed to support the solution.

Design documents must be approved by relevant stakeholders prior to being merged (prototyping).

Software development at GitLab is accomplished using industry standard development practices.

Software development must be accomplished using GitLab’s development platform in a version controlled manner.

Development must adhere to Code review guidelines and secure coding best practices (to avoid introducing vulnerabilities).

Development work must undergo testing and approval prior to deployment to production. This includes configuration changes and other related changes that may not be considered “development” work.

Deployment of software at GitLab must adhere to all defined staging, testing, release, and rollback processes. Details on GitLab’s deployment process can be found here .

After any necessary verification in production is completed, details of changes are pushed to the releases page to be communicated as part of the relevant release notes.

GitLab continuously monitors the state and stability of its platforms.

Maintenance of GitLab’s platform is conducted in accordance with GitLab’s release and maintenance policy .
