"""Questionnaire parsers for xlsx, docx, pdf and csv.

Row identity is preserved wherever the format has one (xlsx rows, csv rows)
so answers can be written back into the original file. Layout detection finds
the header row and the id, question, response and notes columns by name
rather than by fixed position; the v0 fixtures (header row 3, columns A to E)
still resolve the same way. A docx or pdf has no rows: questions are the
numbered items and question-shaped lines, and a pdf question's id carries its
page when the document does not number it.
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
# a pdf is not a zip, but the same bomb exists: a small file whose content
# streams inflate without bound. These are the pdf equivalents of the caps above.
MAX_PDF_PAGES = 400
MAX_PDF_OBJECTS = 100_000
MAX_PDF_INFLATED = MAX_ZIP_UNCOMPRESSED     # summed decoded content streams
MAX_PDF_TEXT = 2_000_000                    # extracted characters


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


_PDF_ID = re.compile(r"^\s*([A-Z]{1,5}[-.]\d+(?:\.\d+)*)\s+(.+)$")     # "AC-01 Is MFA enforced?"
_ASKS = re.compile(r"^(do|does|is|are|how|what|which|describe|provide|please|has|have|can|will)\b", re.I)


def _questions(paras: list[tuple[str, str]]) -> list[RawQuestion]:
    """Numbered items and question-shaped paragraphs; a short line that is
    neither is a section heading and becomes the domain. `paras` pairs each
    paragraph with a fallback id prefix (P for docx, p<page>. for pdf)."""
    out: list[RawQuestion] = []
    domain = ""
    for para, prefix in paras:
        if len(para) < 12:
            continue
        m = _NUMBERED.match(para) or _PDF_ID.match(para)
        if para.isupper() or (len(para) < 60 and not para.endswith("?") and ":" not in para and not m
                              and not _ASKS.match(para)):
            domain = para.rstrip(":")
            continue
        body = m.group(2) if m else para
        qid = m.group(1) if m else ""
        if "?" in body or _ASKS.match(body):
            out.append(RawQuestion(ordinal=len(out) + 1, text=_clean(body), domain=domain,
                                   qid=qid or f"{prefix}{len(out) + 1}"))
            if len(out) >= MAX_QUESTIONS:
                break
    return out


def parse_docx(data: bytes) -> Parsed:
    """Paragraphs and table cells that look like questions. A docx has no row
    identity, so answers cannot be written back in place; export is a new
    document or a csv."""
    from constat.server.extract import extract_text
    text = extract_text("q.docx", data)
    paras = [(p.strip(), "P") for p in text.split("\n") if p.strip()]
    return Parsed(source_kind="docx", questions=_questions(paras),
                  warnings=["docx has no row identity; export produces a new file"])


# ---- pdf ------------------------------------------------------------------
_PAGE_MARK = re.compile(r"^\s*(page\s+)?\d{1,4}(\s*(of|/)\s*\d{1,4})?\s*$", re.I)


def check_pdf(reader) -> None:
    """Refuse a pdf before its text is extracted: encrypted, too many objects
    or pages, or content streams that inflate past the budget. The pdf
    equivalent of check_zip; pypdf's own per-stream limit stays underneath."""
    if reader.is_encrypted:
        raise ValueError("the PDF is password protected; export an unprotected copy")
    objects = int(reader.trailer.get("/Size", 0) or 0)
    if objects > MAX_PDF_OBJECTS:
        raise ValueError(f"PDF declares {objects} objects, above the {MAX_PDF_OBJECTS} cap")
    pages = len(reader.pages)
    if pages > MAX_PDF_PAGES:
        raise ValueError(f"PDF has {pages} pages, above the {MAX_PDF_PAGES} cap")
    total = 0
    for page in reader.pages:
        contents = page.get_contents()
        total += len(contents.get_data()) if contents is not None else 0
        if total > MAX_PDF_INFLATED:
            raise ValueError(f"PDF content inflates past the {MAX_PDF_INFLATED} byte cap")


def _running_lines(pages: list[list[str]]) -> set[str]:
    """Lines that open or close at least half the pages (running headers and
    footers), when there are at least two pages."""
    if len(pages) < 2:
        return set()
    counts: dict[str, int] = {}
    for lines in pages:
        for ln in {*lines[:2], *lines[-2:]}:
            key = re.sub(r"\d+", "#", ln.strip().lower())
            counts[key] = counts.get(key, 0) + 1
    return {k for k, n in counts.items() if n >= max(2, len(pages) / 2)}


def _pdf_items(lines: list[str]) -> list[str]:
    """Re-join wrapped lines into items. A line continues the item before it
    only when that item has not ended its sentence and the line starts in
    lower case; a number, an id, a heading or a capitalised line starts a new
    one. Tuned for questionnaires, where a line ending in "?" ends a question
    whatever its width (the evidence paragraphizer joins those)."""
    items: list[str] = []
    for ln in lines:
        if items and not items[-1].endswith((".", "?", "!", ":")) and ln[:1].islower():
            items[-1] += " " + ln
        else:
            items.append(ln)
    return items


def parse_pdf(data: bytes) -> Parsed:
    """Numbered items and question-shaped lines, page by page. Wrapped lines
    are re-joined first, so a question that wraps is one question. A pdf has
    no row identity; export is a new file."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        check_pdf(reader)
        raw_pages, total = [], 0
        for page in reader.pages:
            t = page.extract_text() or ""
            total += len(t)
            if total > MAX_PDF_TEXT:
                raise ValueError(f"PDF text runs past the {MAX_PDF_TEXT} character cap")
            raw_pages.append([ln for ln in t.splitlines() if ln.strip()])
    except ValueError:
        raise
    except Exception as e:  # noqa: BLE001 - pypdf raises a zoo of types; none may escape as a 500
        raise ValueError(f"not a readable PDF ({type(e).__name__})") from e
    running = _running_lines(raw_pages)
    paras: list[tuple[str, str]] = []
    for n, lines in enumerate(raw_pages, start=1):
        kept = [ln.strip() for ln in lines if not _PAGE_MARK.match(ln)
                and re.sub(r"\d+", "#", ln.strip().lower()) not in running]
        paras.extend((item, f"p{n}.") for item in _pdf_items(kept))
    questions = _questions(paras)
    if not questions:
        raise ValueError("no questions found in the PDF; scanned questionnaires need OCR, which is not supported")
    return Parsed(source_kind="pdf", questions=questions,
                  warnings=["pdf has no row identity; export produces a new file"])


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
    if name.endswith(".pdf"):
        return parse_pdf(data)
    raise ValueError(f"unsupported questionnaire format: {filename}")
