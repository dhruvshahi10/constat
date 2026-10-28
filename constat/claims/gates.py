"""Claim gates. Deterministic, drafter-agnostic, and they run on every answer.

Order:
  0. injection screen on the question           -> REFUSE, quarantine
  1. legal / contractual wording on the question -> HOLD (LEGAL or OWNER)
  2. no covering claim                           -> REFUSE as NOVEL, route by domain owner
  3. claim usable? (deprecated, draft, stale, audience)
  4. certification claim needs certificate-class evidence; a truthful
     negative still needs a human to phrase it
  5. relevance: the claim must cover the question, not a narrower one
  6. parameter missing: the question asks for a value the claim does not hold
  7. completeness: every exception on the claim appears in the answer
  8. absolute language in the answer
  9. contractual wording that the drafter introduced

The outcome is one of ANSWER, HOLD_HUMAN, REFUSE. ANSWER still means "may be
shown to the reviewer"; nothing in this module sends anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..gates import CERT_PAT, CERT_VERB, LEGAL_PAT, _content_words
from .match import Match, key_terms
from .models import Audience, Claim, ClaimStatus, DifficultyClass

RELEVANCE_MIN = 0.5          # share of question key terms the claim bag must cover
RELEVANCE_PARTIAL = 0.25     # below this the claim is treated as not covering
EXCEPTION_MIN = 0.6          # share of an exception's content words that must appear in the answer

INJECTION = [
    re.compile(r"ignore\s+(all|any|the|previous|prior|above).{0,40}(instruction|rule|prompt|polic)", re.I),
    re.compile(r"disregard\s+.{0,40}(instruction|rule|prompt)", re.I),
    re.compile(r"\byou are now\b|\bact as\b.{0,20}\b(admin|system|developer)\b", re.I),
    re.compile(r"(reveal|print|show|dump|repeat|list)\s+(all\s+)?(your\s+|the\s+)?"
               r"(system prompt|instructions|internal|hidden|confidential|api key|secret|claims)", re.I),
    re.compile(r"<\s*/?\s*(system|assistant|tool)\s*>", re.I),
]
CONTRACTUAL = re.compile(
    r"\b(within\s+\d+\s*(hours?|hrs?|days?|business days?)|\d+\s*[-\s]?(hour|day)\s+(sla|notification|window)|"
    r"\bslas?\b|service levels?|guarantee[sd]?|always|never|at all times|100\s*%|indemnif\w*|"
    r"liabilit\w*|penalt\w*|liquidated damages|warrant(y|ies)|contractual(ly)?\s+(commit|oblig)|"
    r"commit(s|ted|ment)?\s+to\b|audit rights?|right to audit|breach notification)", re.I)
ABSOLUTES = re.compile(
    r"\b(100\s*%|completely secure|fully secure|unhackable|zero risk|no risk|never been breached|"
    r"cannot be breached|impossible to|guarantee[sd]?|always|never)\b", re.I)
PARAMETER_ASK = re.compile(
    r"\b(specify|which|what (are|is) (your|the)|how (many|long|often)|within how many|state (the|your)|"
    r"provide (the )?(number|date|version|certificate number)|minimum protocol|versions?|rto|rpo|"
    r"number of days|timeframe|time frame|cadence|frequency|date of)\b", re.I)
HAS_VALUE = re.compile(r"\d|\b(tls|aes|sha|rsa)\b", re.I)
PARAM_WORDS = {"often", "cadence", "frequency", "applied", "apply", "specify", "version", "versions",
               "number", "date", "timeframe", "minimum", "long", "many", "frequently", "summarise",
               "summarize", "detail", "state", "list"}


@dataclass
class Verdict:
    outcome: str                             # ANSWER | HOLD_HUMAN | REFUSE
    difficulty: DifficultyClass
    answer: Optional[str] = None
    claim_id: Optional[str] = None
    claim_version_hash: Optional[str] = None
    route: Optional[str] = None              # LEGAL | OWNER:<email> | DOMAIN_OWNER:<domain>
    flags: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    reused: bool = False

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["difficulty"] = self.difficulty.value
        return d


def _refuse(difficulty, flag, gap, route=None, claim: Claim | None = None) -> Verdict:
    return Verdict(outcome="REFUSE", difficulty=difficulty, route=route, flags=[flag], gaps=[gap],
                   claim_id=claim.claim_id if claim else None,
                   claim_version_hash=claim.version_hash() if claim else None)


def _hold(difficulty, flag, gap, route, claim: Claim | None = None, answer=None) -> Verdict:
    return Verdict(outcome="HOLD_HUMAN", difficulty=difficulty, route=route, flags=[flag], gaps=[gap],
                   answer=answer, claim_id=claim.claim_id if claim else None,
                   claim_version_hash=claim.version_hash() if claim else None)


def screen_question(question: str) -> list[str]:
    """Injection patterns in an inbound question. The normaliser does more
    (tool-less extraction, schema validation, canary); this is the last line."""
    return [p.pattern[:40] for p in INJECTION if p.search(question or "")]


def exception_carried(exception: str, answer: str) -> bool:
    ex = _content_words(exception)
    if not ex:
        return True
    ans = _content_words(answer or "")
    return len(ex & ans) / len(ex) >= EXCEPTION_MIN


def missing_exceptions(claim: Claim, answer: str) -> list[str]:
    return [e for e in claim.exceptions if not exception_carried(e, answer)]


def default_answer(claim: Claim) -> str:
    """The deterministic drafter for claims: statement plus every exception.
    A live model may rephrase; the completeness gate holds it to the same bar."""
    text = claim.statement.strip()
    if claim.exceptions:
        text += " " + " ".join(e.strip().rstrip(".") + "." for e in claim.exceptions)
    return text


def gate(question: str, matches: list[Match], today: date, audience: Audience,
         candidate_answer: Optional[str] = None, domain: str = "",
         domain_owners: dict[str, str] | None = None) -> Verdict:
    """Decide what may happen to one question.

    candidate_answer: the drafted text to judge. None means "use the claim's
    default answer" (statement plus exceptions)."""
    q = question or ""

    # 0. injection
    hits = screen_question(q)
    if hits:
        return _refuse(DifficultyClass.NOVEL, "INJECTION_SUSPECTED",
                       "Inbound question contains instruction-like text; quarantined for the "
                       "account team, not answered.", route="OWNER:security-lead")

    # 1. legal / contractual on the question
    if LEGAL_PAT.search(q):
        return _hold(DifficultyClass.CONTRACTUAL, "LEGAL_COMMITMENT",
                     "Question asks for a legal or contractual commitment; a person decides, "
                     "never drafted as fact.", route="LEGAL")
    contractual_q = bool(CONTRACTUAL.search(q))

    # 2. no covering claim. One shared word is not coverage: a claim counts as
    # covering only if it shares at least two subject terms with the question,
    # or covers half of a very short question.
    def _covers(m: Match) -> bool:
        subj = key_terms(q) - PARAM_WORDS
        shared = subj & set(m.matched_terms)
        return len(shared) >= 2 or (len(subj) <= 2 and m.coverage >= RELEVANCE_MIN)
    usable_matches = [m for m in matches if m.coverage >= RELEVANCE_PARTIAL and _covers(m)]
    if not usable_matches:
        route = f"DOMAIN_OWNER:{(domain_owners or {}).get(domain, domain or 'unassigned')}"
        return _refuse(DifficultyClass.NOVEL, "NO_COVERING_CLAIM",
                       "No claim covers this question. Ask the owner once; the answer becomes "
                       "a claim.", route=route)
    m = usable_matches[0]
    c = m.claim

    # 3. usable?
    ok, why = c.is_usable(today, audience)
    if not ok:
        owner_route = f"OWNER:{c.owner}"
        if why == "DEPRECATED":
            return _refuse(DifficultyClass.COVERED, "DEPRECATED_CLAIM",
                           f"{c.claim_id} is deprecated and may not support an answer.", owner_route, c)
        if why == "DRAFT":
            return _hold(DifficultyClass.COVERED, "DRAFT_CLAIM",
                         f"{c.claim_id} is proposed but not approved; owner must approve before use.",
                         owner_route, c)
        if why == "STALE":
            return _refuse(DifficultyClass.COVERED, "STALE_CLAIM",
                           f"{c.claim_id} v{c.version} expired {c.valid_until.isoformat()}; "
                           f"cannot support a current-state answer. Route to {c.owner} to re-verify.",
                           owner_route, c)
        if why == "AUDIENCE":
            return _refuse(DifficultyClass.COVERED, "AUDIENCE_BLOCKED",
                           f"{c.claim_id} is {c.audience.value}; the request is {audience.value}. "
                           f"Never widened automatically.", owner_route, c)

    # 4. certification
    is_cert_q = bool(CERT_PAT.search(q)) and bool(CERT_VERB.search(q))
    if is_cert_q:
        if not c.has_cert_evidence():
            return _hold(DifficultyClass.COVERED, "CERT_NEEDS_HUMAN",
                         f"Certification question; {c.claim_id} has no certificate or attestation "
                         f"evidence. A truthful negative is phrased by a person, never inferred.",
                         f"OWNER:{c.owner}", c)

    # 5. relevance, measured on the question's subject terms. Words that ask
    # for a value (how often, which version, what cadence) are not subject
    # terms; a claim that states a principle without the value is the
    # parameter-missing case below, not an irrelevant claim.
    subject = key_terms(q) - PARAM_WORDS
    covered = subject & set(m.matched_terms)
    coverage = len(covered) / len(subject) if subject else m.coverage
    if coverage < RELEVANCE_MIN:
        missing = sorted(subject - covered)
        return _hold(DifficultyClass.COVERED, "RELEVANCE_LOW",
                     f"{c.claim_id} covers only {round(coverage * 100)}% of the question's terms; "
                     f"unmatched: {', '.join(missing[:6])}. It may answer a narrower question than "
                     f"the one asked.", f"OWNER:{c.owner}", c)

    # reuse or draft
    if m.reused is not None and candidate_answer is None:
        answer, reused = m.reused.answer, True
        difficulty = DifficultyClass.REUSED
    else:
        answer = candidate_answer if candidate_answer is not None else default_answer(c)
        reused = False
        difficulty = DifficultyClass.COVERED

    # 6. parameter missing
    if PARAMETER_ASK.search(q) and not HAS_VALUE.search(answer) and not HAS_VALUE.search(c.statement):
        return _hold(DifficultyClass.PARAMETER_MISSING, "PARAMETER_MISSING",
                     f"The question asks for a value; {c.claim_id} states a principle without one. "
                     f"Ask {c.owner} for the value once; it becomes part of the claim.",
                     f"OWNER:{c.owner}", c, answer=None)

    # 7. completeness
    omitted = missing_exceptions(c, answer)
    if omitted:
        return _refuse(DifficultyClass.COVERED, "EXCEPTION_OMITTED",
                       f"Answer omits exception(s) the claim carries: " + " | ".join(omitted) +
                       ". True but incomplete is a wrong answer.", f"OWNER:{c.owner}", c)

    # 8. absolutes the drafter introduced
    if ABSOLUTES.search(answer) and not ABSOLUTES.search(c.statement + " " + " ".join(c.exceptions)):
        return _refuse(DifficultyClass.COVERED, "ABSOLUTE_LANGUAGE",
                       "Answer contains absolute language the claim does not support.",
                       f"OWNER:{c.owner}", c)

    # 9. contractual wording, on the question or introduced in the answer
    if contractual_q or (CONTRACTUAL.search(answer) and not CONTRACTUAL.search(c.statement)):
        return _hold(DifficultyClass.CONTRACTUAL, "CONTRACTUAL_WORDING",
                     "SLA, guarantee or commitment wording; a person decides what we commit to.",
                     f"OWNER:{c.owner}", c, answer=answer)

    v = Verdict(outcome="ANSWER", difficulty=difficulty, answer=answer, claim_id=c.claim_id,
                claim_version_hash=c.version_hash(), reused=reused)
    if reused:
        v.flags.append("REUSED_APPROVED_ANSWER")
    if is_cert_q:
        v.flags.append("CERT_CLAIM_EVIDENCED")
    return v
