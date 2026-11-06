<!--
Synthetic fixture. Paraphrased, in our own words, from public pages on
docs.atlan.com, read 2026-11-06. Not Atlan's text and not Atlan-internal
material.
  everything but memory   https://docs.atlan.com/product/capabilities/atlan-ai/concepts/security
  memory                  https://docs.atlan.com/product/capabilities/atlan-ai/references/memory-in-conversational-ai
-->
# Atlan AI security

## Model providers

Atlan AI routes every model call through a central AI gateway to Anthropic Claude on Microsoft Azure, OpenAI GPT models, or open-source models that Atlan hosts.

## Training

Customer metadata, prompts and outputs processed by Atlan AI are not used by Atlan or its AI providers to train or fine-tune foundation models.

## Data sent to model providers

For most AI features, Atlan sends only metadata to AI services. However, conversational AI also sends the user's question, retrieved metadata, lineage, glossary context and session history to the model provider.

## Retention

Full prompts and completions of conversational AI are kept for 30 days in AI observability tooling, tagged by tenant.

Prompts and responses are stored in the tenant's own database, not in the central AI control plane.

## Memory

Conversational memory is personal to each user and is not shown to or reused for other users.

Memory never stores email addresses, phone numbers, government IDs, card numbers, API keys or passwords.
