"""What a question asks about its subject.

"Is customer data in transit logged?" has a subject (customer data in
transit) and a property it asks about (logged). A claim that states the
subject's encryption shares half the question's words and answers a
different question. Relevance measured on one bag of words cannot see
that; this splits the two.

Families are matched on the stems `match.key_terms` produces ("logged" and
"logging" stem to "logg", while the noun "logs" stays "logs"), so "are
audit logs encrypted?" asks about encryption, not about logging. The list
is closed and deliberately small: a property it does not know is treated
as a subject term, which is the behaviour from before it existed.
"""
from __future__ import annotations

import re

PROPERTY_FAMILIES: dict[str, re.Pattern] = {name: re.compile(pat) for name, pat in {
    "encryption": r"encrypt\w*|aes(-\d+)?|cipher\w*|cryptograph\w*|kms|tls",
    "at rest": r"rest|at-rest",
    "in transit": r"transit|in-transit",
    "logging": r"logg\w*",
    "monitoring": r"monitor\w*",
    "backup": r"backups?|back|restor\w*",          # "backed up" stems to "back"
    "deletion": r"delet\w*|purg\w*|eras\w*",
    "retention": r"retain\w*|retention|kept",
    "review": r"review\w*",
    "testing": r"test\w*|pentest|exercis\w*",
    "training": r"train\w*|fine-tun\w*",
    "authentication": r"authent\w*|mfa|multi-factor|2fa|sso|sign-on|passkeys?|passwords?",
    "patching": r"patch\w*",
    "rotation": r"rotat\w*",
    "notification": r"notif\w*|notice",
    "hosting": r"host\w*|regions?|residen\w*|locat\w*",
    "isolation": r"isolat\w*|segregat\w*",
    "revocation": r"revok\w*|revocation|deprovision\w*",
    "scanning": r"scan\w*",
}.items()}


def families(terms: set[str]) -> dict[str, set[str]]:
    """family -> the terms that name it."""
    out: dict[str, set[str]] = {}
    for t in terms:
        for name, pat in PROPERTY_FAMILIES.items():
            if pat.fullmatch(t):
                out.setdefault(name, set()).add(t)
    return out


def property_terms(terms: set[str]) -> set[str]:
    return set().union(*families(terms).values()) if terms else set()
