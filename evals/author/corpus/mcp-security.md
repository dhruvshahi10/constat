<!--
Synthetic fixture. Paraphrased, in our own words, from public pages on
docs.atlan.com, read 2026-11-06. Not Atlan's text and not Atlan-internal
material.
  authentication, permissions, data   https://docs.atlan.com/product/capabilities/atlan-ai/references/mcp-security
  tools                               https://docs.atlan.com/product/capabilities/atlan-ai/references/mcp-tools
-->
# Atlan MCP server security

## Authentication

The Atlan MCP server authenticates every call, either as the signed-in user through OAuth or with an API token or service account. This does not apply to the initial handshake, the only method that runs without authentication.

A service-account token that carries more than one persona is rejected by the MCP server.

## Permissions

The MCP server does not reimplement access control; it forwards the caller's identity so the same persona, role and domain policies as the user interface apply.

The MCP server never widens the access of the login that calls it.

## Tools

By default the MCP server exposes both read and write tools.

MCP tools that change anything return a preview and wait for approval before writing.

Read-only mode removes all write, admin and lifecycle tools from the MCP server and keeps search and lineage.

## Data

The MCP server fetches permission-scoped metadata live from Atlan's REST APIs, without caching.

MCP tool-call logs redact arguments and responses.
