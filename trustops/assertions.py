"""Machine-checkable assertion extraction from policy prose.

Why this exists: `EvidenceStore.contradictions()` groups approved sources by
`assert.*` frontmatter keys and flags two sources that state different values
for the same key. Our synthetic sample pack carries those keys by hand. Until
now an uploaded document carried none, so the contradiction gate, which the
landing page advertises as a live capability, could never fire on a customer's
own evidence. This module reads the crisp, machine-checkable claims that
security policies actually state and turns them into those keys.

Design rule: a false extraction is worse than no extraction. A wrong assertion
manufactures a contradiction, which quarantines a perfectly good source and
routes a real answer to a human for no reason. So every pattern here is
deliberately narrow:

  * the claim must be stated with an explicit window word ("within", "for",
    "no later than", "or higher"), never inferred from a bare mention;
  * the sentence must name the subject the key is about (customer data for a
    deletion window, a breach or incident for a notification window), so a log
    retention period is never mistaken for a customer deletion commitment;
  * if one document states two different values for the same key, we emit
    nothing for that key. A document arguing with itself is not evidence we
    can normalize, and guessing which value wins is exactly the kind of
    inference this product refuses to make elsewhere;
  * negation and deprecation contexts ("TLS 1.0 is disabled") are excluded
    explicitly rather than left to luck.

Units are normalized so that equal commitments compare equal as strings:
durations become whole days (12 months and 365 days both become "365"),
notification windows become whole hours.
"""
from __future__ import annotations

import re

# A month is normalized as 365/12 days precisely so that "12 months" and
# "365 days" land on the same value, which is how policies actually mean them.
# The consequence is that "6 months" (183) and "180 days" are NOT equal, and
# that is correct: they are different commitments in a contract.
DAYS_PER_MONTH = 365 / 12
DAYS_PER_YEAR = 365

MAX_DAYS = 3650          # a 10-year window; anything longer is a parse error
MAX_HOURS = 24 * 90

_DURATION = (r"(?P<num>\d{1,4})[\s-]*"
             r"(?P<unit>calendar\s+days?|business\s+days?|days?|months?|years?)")
_HOURS = r"(?P<num>\d{1,4})[\s-]*(?P<unit>hours?|hrs?|days?)"

# subjects that scope a deletion window to CUSTOMER data, not logs or backups
_CUSTOMER = re.compile(
    r"\b(customer|client|subscriber|personal|end[\s-]user|user)\s+"
    r"(data|content|information|records?|pii)\b|\bpii\b|"
    r"\bpersonal(ly)?[\s-]?identifiable\b", re.I)
_DELETE = re.compile(r"\b(delet\w+|purg\w+|destroy\w+|eras\w+|dispos\w+|sanitiz\w+)\b", re.I)
_RETAIN = re.compile(r"\b(retain\w*|retention)\b", re.I)
_BREACH = re.compile(r"\b(breach(es)?|security incidents?|data incidents?|incidents?)\b", re.I)
_NOTIFY = re.compile(r"\b(notif\w+|inform)\b", re.I)

# a sentence in any of these registers is not stating a live commitment
_NEGATED = re.compile(
    r"\b(not\b|never\b|no longer|disabl\w+|deprecat\w+|prohibit\w+|forbidden|"
    r"unsupported|reject\w+|except|unless|may\s+vary|where\s+feasible|"
    r"aim\s+to|aspir\w+|plan\s+to|intend\s+to|roadmap)", re.I)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text or "") if s.strip()]


def _to_days(num: int, unit: str) -> int | None:
    u = unit.lower().strip()
    if "business" in u:
        return None          # business days depend on a calendar we do not have
    if u.startswith("calendar"):
        u = "day"
    if u.startswith("day"):
        days = num
    elif u.startswith("month"):
        days = round(num * DAYS_PER_MONTH)
    elif u.startswith("year"):
        days = num * DAYS_PER_YEAR
    else:
        return None
    return days if 1 <= days <= MAX_DAYS else None


def _to_hours(num: int, unit: str) -> int | None:
    u = unit.lower().strip()
    if u.startswith(("hour", "hr")):
        hours = num
    elif u.startswith("day"):
        hours = num * 24
    else:
        return None
    return hours if 1 <= hours <= MAX_HOURS else None


# --- individual extractors ---------------------------------------------------
# Each returns the set of distinct values it found. The caller emits a key only
# when a document is internally consistent about it.

_DELETE_WINDOW = re.compile(
    r"(?:within|no\s+later\s+than|not\s+later\s+than|after\s+no\s+more\s+than|"
    r"in\s+no\s+more\s+than)\s+" + _DURATION, re.I)
_RETAIN_WINDOW = re.compile(
    r"(?:for|of|for\s+a\s+period\s+of|period\s+of|up\s+to)\s+" + _DURATION, re.I)


def _deletion_days(text: str) -> set[str]:
    found: set[str] = set()
    for s in _sentences(text):
        if not _CUSTOMER.search(s) or _NEGATED.search(s):
            continue
        if _DELETE.search(s):
            for m in _DELETE_WINDOW.finditer(s):
                d = _to_days(int(m.group("num")), m.group("unit"))
                if d is not None:
                    found.add(str(d))
        if _RETAIN.search(s):
            # only the explicit "retained for N" shape; "retained on a rolling
            # 12-month schedule" is a process description, not a commitment
            for m in _RETAIN_WINDOW.finditer(s):
                if not re.search(r"retain\w*|retention", s[:m.start()], re.I):
                    continue
                d = _to_days(int(m.group("num")), m.group("unit"))
                if d is not None:
                    found.add(str(d))
    return found


_NOTIFY_WINDOW = re.compile(
    r"(?:within|no\s+later\s+than|not\s+later\s+than|in\s+under)\s+" + _HOURS, re.I)


def _breach_notification_hours(text: str) -> set[str]:
    found: set[str] = set()
    for s in _sentences(text):
        if not (_BREACH.search(s) and _NOTIFY.search(s)) or _NEGATED.search(s):
            continue
        for m in _NOTIFY_WINDOW.finditer(s):
            h = _to_hours(int(m.group("num")), m.group("unit"))
            if h is not None:
                found.add(str(h))
    return found


_AES = re.compile(r"\bAES[\s-]?(128|192|256)\b|\b(128|192|256)[\s-]?bit\s+AES\b", re.I)


def _encryption_algorithm(text: str) -> set[str]:
    found: set[str] = set()
    for s in _sentences(text):
        if _NEGATED.search(s):
            continue
        for m in _AES.finditer(s):
            bits = m.group(1) or m.group(2)
            found.add(f"AES-{bits}")
    return found


# A version number only means "minimum" when the sentence says so. A bare
# "TLS 1.0" mention is far more likely to be a deprecation notice.
_TLS_MIN = re.compile(
    r"(?:minimum(?:\s+of)?\s+|at\s+least\s+|no\s+lower\s+than\s+)TLS\s*v?(1\.[0-3])|"
    r"TLS\s*v?(1\.[0-3])\s*(?:or\s+(?:higher|above|greater|later|newer)|and\s+above|\+)|"
    # "the minimum TLS version accepted ... is TLS 1.3": the words may be spread
    # out, but never across a clause break, which is what bounds the gap here
    r"\bminimum\b[^.;,]{0,60}?\bTLS\b[^.;,]{0,60}?v?(1\.[0-3])",
    re.I)


def _minimum_tls_version(text: str) -> set[str]:
    found: set[str] = set()
    for s in _sentences(text):
        if _NEGATED.search(s):
            continue
        for m in _TLS_MIN.finditer(s):
            found.add(m.group(1) or m.group(2) or m.group(3))
    return found


_MFA_REQUIRED = re.compile(
    r"\b(?:mfa|multi[\s-]?factor authentication|2fa|two[\s-]?factor authentication)\b"
    r"[^.;]{0,60}?\b(?:is\s+)?(?:required|mandatory|enforced)\b|"
    r"\b(?:require[sd]?|enforce[sd]?|mandate[sd]?)\b[^.;]{0,40}?"
    r"\b(?:mfa|multi[\s-]?factor authentication|2fa|two[\s-]?factor authentication)\b",
    re.I)


def _mfa_required(text: str) -> set[str]:
    """Deliberately one-sided: we only ever assert "yes".

    "MFA is not required for X" is a scoped exception, not a policy-wide
    negative, and turning it into `mfa_required: no` would manufacture a
    contradiction against a document that correctly says it is required for
    production. Silence is the honest output there.
    """
    for s in _sentences(text):
        if _NEGATED.search(s):
            continue
        if _MFA_REQUIRED.search(s):
            return {"yes"}
    return set()


_PWD_LEN = re.compile(
    r"\b(?:at\s+least|minimum\s+(?:of\s+)?|no\s+fewer\s+than|minimum\s+length\s+of)\s*"
    r"(\d{1,3})\s*characters?\b", re.I)
_PWD_SUBJECT = re.compile(r"\b(password|passphrase)s?\b", re.I)


def _password_min_length(text: str) -> set[str]:
    found: set[str] = set()
    for s in _sentences(text):
        if not _PWD_SUBJECT.search(s) or _NEGATED.search(s):
            continue
        for m in _PWD_LEN.finditer(s):
            n = int(m.group(1))
            if 4 <= n <= 128:
                found.add(str(n))
    return found


EXTRACTORS = {
    "customer_data_deletion_days": _deletion_days,
    "breach_notification_hours": _breach_notification_hours,
    "encryption_algorithm": _encryption_algorithm,
    "minimum_tls_version": _minimum_tls_version,
    "mfa_required": _mfa_required,
    "password_min_length": _password_min_length,
}


def extract_assertions(text: str) -> dict[str, str]:
    """Return {assert_key: normalized_value} for unambiguous claims only.

    A key whose extractors disagree within one document is dropped: we would be
    guessing, and a guessed assertion becomes a fabricated contradiction.
    """
    out: dict[str, str] = {}
    for key, fn in EXTRACTORS.items():
        values = fn(text or "")
        if len(values) == 1:
            out[key] = next(iter(values))
    return out
