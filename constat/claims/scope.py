"""Product and data-class context for claims.

A fact true of one product is not evidence about another: "metadata is
encrypted at rest in the catalog" says nothing about the prompts an AI
feature sends to a model provider. Questionnaires name the product and the
data they ask about; a claim says which ones it covers. This module is the
shared vocabulary for both sides, deterministic and closed: a term that is
not listed here is not detected, and a claim may only declare listed slugs.

Detection runs on canonical text (`gates.canon`) so a zero-width split or
an NFKC variant of "MCP" is still MCP.
"""
from __future__ import annotations

import re

# slug -> pattern that names it in a question or a claim's own text. Kept
# narrow on purpose: a false detection holds a good answer for a person, a
# missed one lets a claim answer for a product it never mentioned.
PRODUCTS: dict[str, re.Pattern] = {
    "catalog": re.compile(r"\b(data catalog|catalog(ue)?|business glossary|data lineage)\b", re.I),
    "ai-features": re.compile(
        r"\b(ai|artificial intelligence|gen[\s-]?ai|generative|llms?|large language models?|"
        r"copilots?|ai assistants?|ai agents?|machine learning)\b", re.I),
    "mcp": re.compile(r"\b(mcp|model context protocol)\b", re.I),
}
DATA_CLASSES: dict[str, re.Pattern] = {
    "metadata": re.compile(r"\bmeta[\s-]?data\b", re.I),
    "customer-data": re.compile(r"\b(customer|client|tenant)[\s'’-]*s?[\s'’-]*data\b|\b(our|my) data\b", re.I),
    "prompts": re.compile(r"\b(prompts?|chat (history|messages)|conversation history)\b", re.I),
}
DEPLOYMENTS = {"saas-multi-tenant", "saas-single-tenant", "self-hosted", "hybrid"}
LABEL = {"catalog": "the catalog", "ai-features": "AI features", "mcp": "the MCP server",
         "metadata": "metadata", "customer-data": "customer data", "prompts": "prompts"}


def detect(text: str, vocab: dict[str, re.Pattern]) -> set[str]:
    return {slug for slug, pat in vocab.items() if pat.search(text or "")}


def named_products(text: str) -> set[str]:
    return detect(text, PRODUCTS)


def named_data_classes(text: str) -> set[str]:
    return detect(text, DATA_CLASSES)


def effective_scope(claim) -> tuple[set[str], set[str]]:
    """What a claim covers, per dimension. A declared list is authoritative.
    An empty list falls back to what the claim's own statement and scope text
    name, so a legacy claim reading "Customer data at rest is encrypted"
    still covers customer data, and one that names no product covers none.
    Exceptions are not read: "excludes prompts" must not make a claim cover
    prompts."""
    own_text = f"{claim.statement} {claim.scope}"
    products = set(claim.products) if claim.products else named_products(own_text)
    classes = set(claim.data_classes) if claim.data_classes else named_data_classes(own_text)
    return products, classes


def scope_gaps(question: str, claim) -> list[str]:
    """Products and data classes the question names that the claim does not
    cover, as slugs, products first."""
    products, classes = effective_scope(claim)
    return (sorted(named_products(question) - products)
            + sorted(named_data_classes(question) - classes))


def validate_scope(products: list[str], data_classes: list[str], deployment: str) -> list[str]:
    problems = []
    for p in products:
        if p not in PRODUCTS:
            problems.append(f"unknown product {p!r}; known: {', '.join(sorted(PRODUCTS))}")
    for d in data_classes:
        if d not in DATA_CLASSES:
            problems.append(f"unknown data class {d!r}; known: {', '.join(sorted(DATA_CLASSES))}")
    if deployment and deployment not in DEPLOYMENTS:
        problems.append(f"unknown deployment {deployment!r}; known: {', '.join(sorted(DEPLOYMENTS))}")
    return problems
