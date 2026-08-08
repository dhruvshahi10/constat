"""Ingest and structure-preserving export.

Contract (blueprint p.10, definition of done):
  - import a real XLSX and preserve identifiers and order on export
  - write ONLY the response/notes columns; question text is never modified
  - merged cells, hidden rows, and formulas survive the round trip

Row identity is carried on the Question object itself (q.row), so export is a
positional write-back, not a fuzzy match.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font

from .models import Draft, Question

HEADER_ROW = 3
COL_ID, COL_DOMAIN, COL_Q, COL_RESP, COL_NOTES = 1, 2, 3, 4, 5


def ingest_questionnaire(path: Path) -> list[Question]:
    wb = load_workbook(path)
    ws = wb.active
    out: list[Question] = []
    for row in range(HEADER_ROW + 1, ws.max_row + 1):
        qid = ws.cell(row=row, column=COL_ID).value
        qtext = ws.cell(row=row, column=COL_Q).value
        if not qid or not qtext or not isinstance(qid, str):
            continue  # blank spacer rows / formula footer
        out.append(Question(
            question_id=qid.strip(),
            row=row,
            domain=str(ws.cell(row=row, column=COL_DOMAIN).value or "").strip(),
            text=str(qtext).strip(),
        ))
    return out


def _response_text(d: Draft) -> str:
    if d.answer:
        return d.answer
    if d.route == "LEGAL":
        return "[ROUTED TO LEGAL] Contractual commitment — not drafted by the answer engine."
    return "[ABSTAINED] Insufficient approved evidence — see exception notes."


def _notes_text(d: Draft) -> str:
    parts = []
    if d.citations:
        parts.append("Evidence: " + "; ".join(
            f"{c.source_id} v{c.version} ({c.location})" for c in d.citations))
    if d.gaps:
        parts.append("Gaps: " + " | ".join(d.gaps))
    if d.route:
        parts.append(f"Routed: {d.route}")
    parts.append(f"[coverage={d.evidence_coverage.value} risk={d.risk.value} "
                 f"human_review={'yes' if d.requires_human else 'approved'}]")
    return "\n".join(parts)


def export_answers(src: Path, dst: Path, questions: list[Question],
                   drafts: dict[str, Draft]) -> None:
    wb = load_workbook(src)   # default load: formulas preserved as formulas
    ws = wb.active
    body = Font(name="Arial", size=10)
    wrap = Alignment(wrap_text=True, vertical="top")
    for q in questions:
        d = drafts[q.question_id]
        # write ONLY the response columns; never touch COL_ID / COL_Q
        rc = ws.cell(row=q.row, column=COL_RESP, value=_response_text(d))
        nc = ws.cell(row=q.row, column=COL_NOTES, value=_notes_text(d))
        rc.font = body; rc.alignment = wrap
        nc.font = body; nc.alignment = wrap
    wb.save(dst)
