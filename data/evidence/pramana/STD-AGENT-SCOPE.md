---
source_id: STD-AGENT-SCOPE
title: Agent Permissions and MCP Exposure Standard
type: standard
version: 1.0
effective_date: 2026-08-24
expiry_date: 2027-08-24
owner: dhruv.shahi07@gmail.com
approval_status: approved
topics: agent permissions, mcp, ai governance, access control, model access
---

No MCP server is exposed. Pramana does not run, publish or embed a Model Context Protocol server, and exposes no tool surface to any external agent. There is no endpoint through which a third-party model or agent can query a tenant's evidence.

No autonomous agent loop. The engine is a fixed pipeline, not an agent. Its stages run in a determined order: ingest, classify, retrieve, draft, gate, route, export. The model is called once per question and cannot decide to call itself again, call a tool, browse, or take an action. There is no planner and no self-directed control flow.

Capability inventory of the model call. The drafter's total capability is: read the supplied excerpts, return a JSON object. It holds no credential, cannot write to disk, cannot reach the audit log, cannot alter a source's approval status, and cannot cause an export.

Network egress. In deterministic mode the engine makes no outbound network calls at all. With a live drafter enabled, the only outbound destination is the selected model provider's API endpoint.

Public surface. The hosted site exposes two endpoints: one that answers a question against a synthetic corpus using the deterministic drafter, and one that records an early-access email address. Neither accepts a file upload, neither writes to the evidence corpus, and neither exposes an operator's corpus.
