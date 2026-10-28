"""Quarantine: inbound questionnaire text is data, never instructions.

Three checks, each of which can only add to quarantine:
  1. pattern screen on the raw text (prompt-injection phrasing, markup that
     impersonates a chat role, spreadsheet formula injection, control and
     zero-width characters used to hide text)
  2. canary: the normaliser is told to emit a per-call token if the input asks
     it to reveal or change its instructions; the token in its output means
     the input tried
  3. an optional model classifier, which may flag but never clear
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..claims.gates import INJECTION, screen_question

FORMULA = re.compile(r"^\s*[=+\-@]\s*[A-Za-z(]")                 # =HYPERLINK(, +cmd|, @SUM(
ROLE_MARKUP = re.compile(r"<\s*/?\s*(system|assistant|user|tool|instruction)s?\s*>|\[(INST|SYS)\]", re.I)
HIDDEN = re.compile(r"[​‌‍⁠﻿‪-‮⁦-⁩]")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
BASE64ISH = re.compile(r"\b[A-Za-z0-9+/]{80,}={0,2}\b")


@dataclass
class QuarantineDecision:
    quarantined: bool
    reasons: list[str] = field(default_factory=list)

    def add(self, reason: str) -> None:
        self.quarantined = True
        self.reasons.append(reason)


def screen_raw(text: str) -> QuarantineDecision:
    d = QuarantineDecision(False)
    if screen_question(text):
        d.add("instruction-like phrasing (prompt injection pattern)")
    if ROLE_MARKUP.search(text):
        d.add("chat-role markup inside questionnaire text")
    if FORMULA.match(text):
        d.add("spreadsheet formula at the start of a cell (formula injection)")
    if HIDDEN.search(text):
        d.add("zero-width or bidirectional control characters (hidden text)")
    if CONTROL.search(text):
        d.add("control characters in text")
    if BASE64ISH.search(text):
        d.add("long base64-like blob in a question")
    # homoglyph check: letters outside Latin, Greek and Cyrillic scripts mixed into ASCII words
    for ch in text:
        if ch.isalpha() and ord(ch) > 0x24F and unicodedata.category(ch).startswith("L"):
            name = unicodedata.name(ch, "")
            if "LATIN" not in name and "GREEK" not in name and "CYRILLIC" not in name and "CJK" not in name \
                    and "DEVANAGARI" not in name and "ARABIC" not in name and "HEBREW" not in name:
                d.add(f"unusual script character {ch!r} inside question text")
                break
    return d


def screen_output(output_text: str, canary: str) -> QuarantineDecision:
    d = QuarantineDecision(False)
    if canary and canary in output_text:
        d.add("normaliser emitted the canary: the input asked it to reveal or change instructions")
    if any(p.search(output_text) for p in INJECTION):
        d.add("instruction-like phrasing survived into the normalised output")
    return d


CUSTOMER_NOTE = (
    "One or more items in your questionnaire contained text that reads as instructions to an "
    "automated system rather than as a question. We have set those items aside and will answer "
    "them by hand. If this was deliberate on your side, for example a red-team exercise, please "
    "let us know; if not, the template may have been altered and is worth checking."
)
