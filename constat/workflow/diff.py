"""Word-level diff between a draft and the last approved answer, as ops the
UI renders with ins/del styling. Stdlib difflib, deterministic."""
from __future__ import annotations

import difflib
import re

_TOK = re.compile(r"\s+|[^\s]+")


def word_diff(old: str, new: str) -> list[dict]:
    a = [t for t in _TOK.findall(old or "") if t]
    b = [t for t in _TOK.findall(new or "") if t]
    ops: list[dict] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append({"op": "equal", "text": "".join(a[i1:i2])})
        else:
            if i2 > i1:
                ops.append({"op": "del", "text": "".join(a[i1:i2])})
            if j2 > j1:
                ops.append({"op": "ins", "text": "".join(b[j1:j2])})
    return ops


def edit_distance_ratio(old: str, new: str) -> float:
    """0.0 identical, 1.0 entirely different; feeds the human edit rate."""
    if not old and not new:
        return 0.0
    return round(1.0 - difflib.SequenceMatcher(a=old or "", b=new or "", autojunk=False).ratio(), 3)
