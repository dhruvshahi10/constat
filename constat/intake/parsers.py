"""Questionnaire parsers for xlsx, docx and csv.

Row identity is preserved wherever the format has one (xlsx rows, csv rows)
so answers can be written back into the original file. Layout detection finds
the header row and the id, question, response and notes columns by name
rather than by fixed position; the v0 fixtures (header row 3, columns A to E)
still resolve the same way.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

QUESTION_HDR = re.compile(r"question|control|requirement|query|ask", re.I)
ID_HDR = re.compile(r"(^|\b)(id|ref|reference|#|no\.?|number)(\b|$)", re.I)
DOMAIN_HDR = re.compile(r"domain|category|section|area|topic", re.I)
RESPONSE_HDR = re.compile(r"response|answer|vendor|reply|supplier", re.I)
NOTES_HDR = re.compile(r"note|comment|evidence|remark|reference doc", re.I)
MAX_QUESTIONS = 2000
MAX_TEXT = 4000
MAX_ZIP_UNCOMPRESSED = 64 * 1024 * 1024    # xlsx and docx are zips; this is the inflated cap
MAX_ZIP_ENTRIES = 2000
MAX_SHEET_CELLS = 2_000_000


def check_zip(path: Path) -> None:
    """Refuse decompression bombs before any parser inflates them."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise ValueError(f"archive has {len(infos)} entries, above the {MAX_ZIP_ENTRIES} cap")
            total = sum(i.file_size for i in infos)
            if total > MAX_ZIP_UNCOMPRESSED:
                raise ValueError(f"archive inflates to {total} bytes, above the {MAX_ZIP_UNCOMPRESSED} cap")
    except zipfile.BadZipFile as e:
        raise ValueError("not a valid Office file") from e


@dataclass
class RawQuestion:
    ordinal: int
    text: str
    domain: str = ""
    qid: str = ""
    row: Optional[int] = None          # 1-based source row where one exists
    answer: str = ""                   # the response column, when the file is already answered


@dataclass
class Layout:
    header_row: int = 0
    col_id: Optional[int] = None
    col_domain: Optional[int] = None
    col_question: Optional[int] = None
    col_response: Optional[int] = None
    col_notes: Optional[int] = None
    sheet: str = ""


@dataclass
class Parsed:
    source_kind: str
    questions: list[RawQuestion]
    layout: Layout = field(default_factory=Layout)
    warnings: list[str] = field(default_factory=list)


def _clean(v) -> str:
    s = "" if v is None else str(v)
    return " ".join(s.split())[:MAX_TEXT]


# ---- xlsx -----------------------------------------------------------------
def detect_layout(ws) -> Layout:
    """Scan the first 15 rows for a header that names a question column."""
    for r in range(1, min(ws.max_row, 15) + 1):
        cells = [(c, _clean(ws.cell(row=r, column=c).value)) for c in range(1, min(ws.max_column, 30) + 1)]
        named = [(c, v) for c, v in cells if v]
        if len(named) < 2:
            continue
        # the id column is found first so "Question ID" is never taken as the question column
        ids = [c for c, v in named if ID_HDR.search(v)]
        q = next((c for c, v in named if QUESTION_HDR.search(v) and not RESPONSE_HDR.search(v)
                  and c not in ids), None)
        if q is None:
            continue
        lay = Layout(header_row=r, col_question=q, sheet=ws.title, col_id=ids[0] if ids else None)
        for c, v in named:
            if c == q or c == lay.col_id:
                continue
            elif lay.col_domain is None and DOMAIN_HDR.search(v):
                lay.col_domain = c
            elif lay.col_response is None and RESPONSE_HDR.search(v):
                lay.col_response = c
            elif lay.col_notes is None and NOTES_HDR.search(v):
                lay.col_notes = c
        return lay
    raise ValueError("no header row with a question column found in the first 15 rows")


def parse_xlsx(path: Path) -> Parsed:
    from openpyxl import load_workbook
    check_zip(path)
    wb = load_workbook(path, read_only=False, data_only=True)
    ws = wb.active
    if ws.max_row * max(1, ws.max_column) > MAX_SHEET_CELLS:
        raise ValueError("sheet is larger than the cell cap")
    # a formula in a question cell has no cached value when the file was never
    # calculated, and data_only reads it as None. Read the formula text too, so
    # a cell that starts with "=" reaches quarantine instead of vanishing.
    ws_formulas = load_workbook(path, read_only=False, data_only=False).active
    lay = detect_layout(ws)
    out: list[RawQuestion] = []
    warnings: list[str] = []
    for r in range(lay.header_row + 1, ws.max_row + 1):
        text = _clean(ws.cell(row=r, column=lay.col_question).value)
        qid = _clean(ws.cell(row=r, column=lay.col_id).value) if lay.col_id else ""
        if not text:
            raw_formula = ws_formulas.cell(row=r, column=lay.col_question).value
            if isinstance(raw_formula, str) and raw_formula.startswith("="):
                if lay.col_id and not qid:
                    # a formula below the table (a COUNTA footer, a total) is not a question;
                    # a formula inside a numbered row still is, and reaches quarantine
                    warnings.append(f"row {r}: formula cell outside the question rows skipped")
                    continue
                text = _clean(raw_formula)
        if not text:
            continue
        dom = _clean(ws.cell(row=r, column=lay.col_domain).value) if lay.col_domain else ""
        ans = _clean(ws.cell(row=r, column=lay.col_response).value) if lay.col_response else ""
        out.append(RawQuestion(ordinal=len(out) + 1, text=text, domain=dom, qid=qid or f"R{r}", row=r, answer=ans))
        if len(out) >= MAX_QUESTIONS:
            warnings.append(f"stopped at {MAX_QUESTIONS} questions")
            break
    if lay.col_response is None:
        warnings.append("no response column found; answers will be exported to a new column")
    return Parsed(source_kind="xlsx", questions=out, layout=lay, warnings=warnings)


def write_xlsx(src: Path, dst: Path, layout: Layout, answers: dict[int, tuple[str, str]]) -> None:
    """Write (response, notes) per source row into a copy of the workbook.
    Only the response and notes columns are touched; the question, id and
    every other cell, merged range, hidden row and formula stay as they were."""
    from openpyxl import load_workbook
    wb = load_workbook(src)
    ws = wb[layout.sheet] if layout.sheet in wb.sheetnames else wb.active
    col_resp = layout.col_response or (ws.max_column + 1)
    col_notes = layout.col_notes or (col_resp + 1)
    if layout.col_response is None:
        ws.cell(row=layout.header_row, column=col_resp, value="Response")
        ws.cell(row=layout.header_row, column=col_notes, value="Notes")
    for row, (resp, notes) in answers.items():
        ws.cell(row=row, column=col_resp, value=resp)
        ws.cell(row=row, column=col_notes, value=notes)
    wb.save(dst)


# ---- csv ------------------------------------------------------------------
def parse_csv(data: bytes) -> Parsed:
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    for hi, hdr in enumerate(rows[:15]):
        ids = [i for i, v in enumerate(hdr) if ID_HDR.search(v or "")]
        q = next((i for i, v in enumerate(hdr) if QUESTION_HDR.search(v or "") and not RESPONSE_HDR.search(v or "")
                  and i not in ids), None)
        if q is None:
            continue
        lay = Layout(header_row=hi + 1, col_question=q + 1, col_id=(ids[0] + 1) if ids else None)
        for i, v in enumerate(hdr):
            v = v or ""
            if i == q or (lay.col_id and i == lay.col_id - 1):
                continue
            elif lay.col_domain is None and DOMAIN_HDR.search(v):
                lay.col_domain = i + 1
            elif lay.col_response is None and RESPONSE_HDR.search(v):
                lay.col_response = i + 1
        out = []
        for r, row in enumerate(rows[hi + 1:], start=hi + 2):
            if q >= len(row):
                continue
            t = _clean(row[q])
            if not t:
                continue
            qid = _clean(row[lay.col_id - 1]) if lay.col_id and lay.col_id - 1 < len(row) else ""
            dom = _clean(row[lay.col_domain - 1]) if lay.col_domain and lay.col_domain - 1 < len(row) else ""
            ans = _clean(row[lay.col_response - 1]) if lay.col_response and lay.col_response - 1 < len(row) else ""
            out.append(RawQuestion(ordinal=len(out) + 1, text=t, domain=dom, qid=qid or f"R{r}", row=r, answer=ans))
        return Parsed(source_kind="csv", questions=out, layout=lay)
    raise ValueError("no header row with a question column found")


# ---- docx -----------------------------------------------------------------
_NUMBERED = re.compile(r"^\s*(?:(\d+(?:\.\d+)*|[A-Z]{1,4}-\d+(?:\.\d+)?|[a-z]|[ivx]+)[.):\]]\s+)(.+)$")


def parse_docx(data: bytes) -> Parsed:
    """Paragraphs and table cells that look like questions. A docx has no row
    identity, so answers cannot be written back in place; export is a new
    document or a csv."""
    from constat.server.extract import extract_text
    text = extract_text("q.docx", data)
    out: list[RawQuestion] = []
    domain = ""
    for para in [p.strip() for p in text.split("\n") if p.strip()]:
        if len(para) < 12:
            continue
        if para.isupper() or (len(para) < 60 and not para.endswith("?") and ":" not in para and not _NUMBERED.match(para)):
            domain = para.rstrip(":")
            continue
        m = _NUMBERED.match(para)
        body = m.group(2) if m else para
        qid = m.group(1) if m else ""
        if "?" in body or re.match(r"^(do|does|is|are|how|what|which|describe|provide|please|has|have|can|will)\b", body, re.I):
            out.append(RawQuestion(ordinal=len(out) + 1, text=_clean(body), domain=domain, qid=qid or f"P{len(out) + 1}"))
    return Parsed(source_kind="docx", questions=out, warnings=["docx has no row identity; export produces a new file"])


def parse(filename: str, data: bytes, tmp_dir: Path) -> Parsed:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        p = tmp_dir / "upload.xlsx"
        p.write_bytes(data)
        return parse_xlsx(p)
    if name.endswith(".csv"):
        return parse_csv(data)
    if name.endswith(".docx"):
        return parse_docx(data)
    raise ValueError(f"unsupported questionnaire format: {filename}")
