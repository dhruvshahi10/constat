<!--
Synthetic fixture. Paraphrased, in our own words, from public pages on
docs.atlan.com, read 2026-11-06. Not Atlan's text and not Atlan-internal
material. Each section names the page it paraphrases.
  encryption         https://docs.atlan.com/platform/concepts/encryption-and-key-management
  what is stored     https://docs.atlan.com/platform/concepts/data-and-metadata-persistence
  tenant isolation   https://docs.atlan.com/platform/references/how-are-resources-isolated
  identity           https://docs.atlan.com/product/integrations/identity-management/sso
                     https://docs.atlan.com/product/integrations/identity-management/scim/how-tos/configure-scim-provisioning
  testing            https://docs.atlan.com/platform/references/infrastructure-security
  compliance         https://docs.atlan.com/platform/references/compliance-standards-and-assessments
  logs               https://docs.atlan.com/product/administration/logs/how-tos/view-query-logs
-->
# Platform security

## Encryption

Atlan encrypts data at rest with AES-256 across its object storage and volumes on AWS, Azure and GCP. However, storage encryption uses keys managed by the cloud provider, not by the customer.

Atlan encrypts data in transit with HTTPS and TLS.

Atlan keeps its encryption keys and secrets in Vault.

## What the catalog stores

The catalog stores crawled asset metadata and user data inside an Atlan-managed VPC.

Customer data stays in the source system, and query results are streamed to the user and are not cached.

## Tenant isolation

Each tenant runs on isolated compute nodes with its own Cassandra, Elasticsearch and object storage, and its own IAM roles. This does not apply to the Kubernetes control plane, which is shared between tenants and separated logically with virtual clusters.

## Identity

Atlan supports SAML 2.0 single sign-on with any SAML-compatible identity provider.

Atlan supports SCIM 2.0 provisioning and deprovisioning of users and groups from Okta and Microsoft Entra ID.

## Testing

An independent penetration test of the application is commissioned every year.

## Compliance

Atlan is listed as ISO 27001, SOC 2 Type II and ISO 27701 certified on its compliance standards page.

## Logs

Query logs cover queries from the editor, the API and sample previews, and are kept for the life of the instance.

Connector event logs are kept for 7 days.
