"""Uploaded document -> approved evidence source.

Every failure is a clean, actionable ExtractError; nothing half-extracted is
ever persisted. The synthesized frontmatter is validated by parse_source()
itself before the file is written — the same reader the pipeline uses — so an
upload that persists is by construction ingestible.
"""
from __future__ import annotations

import hashlib
import io
import re
from datetime import date
from pathlib import Path

from ..assertions import extract_assertions
from ..evidence import parse_source
from . import config

TYPE_PREFIX = {
    "policy": "POL", "standard": "STD", "plan": "PLN", "report": "RPT",
    "attestation": "ATT", "certificate": "CRT", "roadmap": "RMP", "register": "REG",
}
ALLOWED_EXT = {".pdf", ".docx", ".md", ".txt"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ExtractError(ValueError):
    """message is safe to show the uploader verbatim."""


# --- PDF paragraph reconstruction --------------------------------------------
# evidence.chunks() splits a source body on blank lines, so ONE BLANK LINE IS
# ONE CHUNK, and a chunk is the unit of retrieval and of the citation location
# printed in the provenance strip. pypdf hands back a page as wrapped display
# lines joined by single newlines. Joining pages with "\n\n" and nothing else
# therefore made a whole PDF page into a single chunk: retrieval got coarse, the
# location "para:1" meant "somewhere on page 1", and the excerpt handed to a
# model was a page rather than a passage. Here we rebuild paragraphs inside each
# page so that a chunk is a paragraph again.
#
# Blank lines already present in the extraction are genuine author breaks and
# are always preserved. Inside a run of consecutive lines we only introduce a
# break where the layout says one exists: a bullet or numbered item starts, an
# ALL CAPS or numbered heading starts, or a line both ends a sentence and is
# noticeably shorter than the page's typical line width (the classic end-of-
# paragraph short line). Everything else is re-joined into flowing prose.
_BULLET_RE = re.compile(r"^\s*(?:[-–—•*·•●▪]|\(\d{1,2}\)|\d{1,2}[.)]\s|[a-z]\)\s)")
_HEADING_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\s+[A-Z]|[A-Z][A-Z0-9 ,/&()'\-]{4,}\s*$)")
_SHORT_LINE_RATIO = 0.85


def _paragraphize_page(page: str) -> str:
    out: list[str] = []
    for block in re.split(r"\n\s*\n", page):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        widths = sorted(len(ln) for ln in lines)
        typical = widths[len(widths) // 2] or 1
        current: list[str] = []
        for ln in lines:
            if current and (_BULLET_RE.match(ln) or _HEADING_RE.match(ln)):
                out.append(" ".join(current))
                current = []
            current.append(ln)
            if (ln.endswith((".", "!", "?", ":", ";"))
                    and len(ln) < _SHORT_LINE_RATIO * typical):
                out.append(" ".join(current))
                current = []
        if current:
            out.append(" ".join(current))
    return "\n\n".join(p for p in out if p)


# A 5MB upload gate bounds what arrives on the wire, not what it becomes in
# memory. A re-audit built two working bombs that pass that gate: a 0.41MB DOCX
# whose document.xml inflates to 400MB (826MB peak RSS), and a 0.44MB DOCX of
# 1.2 million paragraphs that took 68 seconds of GIL-holding CPU and 1.1GB RSS
# before the post-extraction character check fired. Render starter is 512MB, so
# either one is a single-request OOM kill that takes the run worker, the queue
# and every in-flight run with it. The budget has to be enforced BEFORE and
# DURING extraction, never after.
MAX_PDF_PAGES = 400
MAX_DOCX_PARAGRAPHS = 20_000
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024   # what a legitimate policy can expand to


def _too_big(what: str) -> ExtractError:
    return ExtractError(
        f"This file expands to more than we process in one document ({what}). "
        "Split it and upload the relevant sections.")


def _accumulate(parts, cap: int, what: str) -> str:
    """Join text while watching the running total, so a pathological document
    is refused at the point it exceeds budget rather than after it is all in
    memory."""
    out, total = [], 0
    for part in parts:
        if not part:
            continue
        total += len(part)
        if total > cap:
            raise _too_big(what)
        out.append(part)
    return "\n\n".join(out)


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        n_pages = len(reader.pages)
        if n_pages > MAX_PDF_PAGES:
            raise _too_big(f"{n_pages} pages, limit {MAX_PDF_PAGES}")
        pages = (p.extract_text() for p in reader.pages)
        text = _accumulate((_paragraphize_page(p) for p in pages if p),
                           config.MAX_EXTRACT_CHARS, "too much text")
    except ExtractError:
        raise
    except Exception as exc:  # noqa: BLE001 — pypdf raises a zoo of types
        raise ExtractError(f"Could not read this PDF ({type(exc).__name__}). "
                           "Is the file corrupt or password protected?") from exc
    if not text.strip():
        raise ExtractError("No extractable text in this PDF. Scanned documents "
                           "need OCR, which is not supported yet.")
    return text


def _docx_uncompressed_size(data: bytes) -> None:
    """Refuse a decompression bomb from the zip directory, before any parsing.

    python-docx sets resolve_entities=False so XXE is closed, but nothing bounds
    how far a deflate stream expands, and lxml materializes document.xml whole.
    """
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            total = sum(i.file_size for i in z.infolist())
    except zipfile.BadZipFile as exc:
        raise ExtractError("This DOCX is not a readable Office file.") from exc
    if total > MAX_UNCOMPRESSED_BYTES:
        raise _too_big(f"{total // (1024 * 1024)}MB uncompressed, "
                       f"limit {MAX_UNCOMPRESSED_BYTES // (1024 * 1024)}MB")


def _docx_text(data: bytes) -> str:
    _docx_uncompressed_size(data)
    try:
        import docx
        d = docx.Document(io.BytesIO(data))
        paras = d.paragraphs
        if len(paras) > MAX_DOCX_PARAGRAPHS:
            raise _too_big(f"{len(paras)} paragraphs, limit {MAX_DOCX_PARAGRAPHS}")
        text = _accumulate((p.text for p in paras if p.text.strip()),
                           config.MAX_EXTRACT_CHARS, "too much text")
    except ExtractError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ExtractError(f"Could not read this DOCX ({type(exc).__name__}).") from exc
    if not text.strip():
        raise ExtractError("No text found in this DOCX.")
    return text


def _plain_text(data: bytes, kind: str) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractError(f"This {kind} file is not valid UTF-8 text.") from exc
    if kind == "md":
        # never trust uploaded frontmatter; ours is synthesized from the form
        text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    if not text.strip():
        raise ExtractError(f"This {kind} file is empty.")
    return text


def extract_text(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ExtractError(f"Unsupported file type '{ext}'. "
                           "Accepted: PDF, DOCX, MD, TXT.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ExtractError("File exceeds the 5MB limit.")
    if ext == ".pdf":
        text = _pdf_text(data)
    elif ext == ".docx":
        text = _docx_text(data)
    else:
        text = _plain_text(data, ext.lstrip("."))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > config.MAX_EXTRACT_CHARS:
        raise ExtractError("Extracted text exceeds the 200,000 character limit. "
                           "Split the document and upload the relevant sections.")
    return text


def _slug_fragment(title: str) -> str:
    s = re.sub(r"[^A-Z0-9]+", "-", title.upper()).strip("-")[:12].rstrip("-")
    return s or "DOC"


def make_source_id(doc_type: str, title: str, sha: str) -> str:
    return f"{TYPE_PREFIX[doc_type]}-{_slug_fragment(title)}-{sha[:4].upper()}"


def validate_meta(form: dict[str, str]) -> dict[str, str]:
    """Validates upload-form metadata; returns cleaned fields or raises."""
    title = form.get("title", "").strip()
    if not 2 <= len(title) <= 120:
        raise ExtractError("Title must be 2 to 120 characters.")
    doc_type = form.get("type", "").strip().lower()
    if doc_type not in TYPE_PREFIX:
        raise ExtractError(f"Type must be one of: {', '.join(sorted(TYPE_PREFIX))}.")
    version = form.get("version", "").strip() or "1.0"
    owner = form.get("owner", "").strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", owner):
        raise ExtractError("Owner must be an email address (who maintains this document).")
    eff = form.get("effective_date", "").strip()
    exp = form.get("expiry_date", "").strip()
    for label, val in (("Effective date", eff), ("Expiry date", exp)):
        if not DATE_RE.match(val):
            raise ExtractError(f"{label} must be YYYY-MM-DD.")
        try:
            date.fromisoformat(val)
        except ValueError:
            raise ExtractError(f"{label} is not a real date.") from None
    if date.fromisoformat(exp) <= date.fromisoformat(eff):
        raise ExtractError("Expiry date must be after the effective date.")
    topics = form.get("topics", "").strip()
    attested = form.get("attested", "") in ("on", "true", "1", "yes")
    return {"title": title, "type": doc_type, "version": version, "owner": owner,
            "effective_date": eff, "expiry_date": exp, "topics": topics,
            "approval_status": "approved" if attested else "draft"}


def synthesize(meta: dict[str, str], body: str, tenant: str) -> tuple[str, str, str]:
    """Returns (source_id, sha256-of-extracted-text, file_text). Validated by
    parse_source before return — what comes back is guaranteed ingestible."""
    sha = hashlib.sha256(body.encode()).hexdigest()
    source_id = make_source_id(meta["type"], meta["title"], sha)
    lines = [
        "---",
        f"source_id: {source_id}",
        f"title: {meta['title']}",
        f"type: {meta['type']}",
        f'version: "{meta["version"]}"',
        f"effective_date: {meta['effective_date']}",
        f"expiry_date: {meta['expiry_date']}",
        f"owner: {meta['owner']}",
        f"approval_status: {meta['approval_status']}",
    ]
    if meta["topics"]:
        lines.append(f"topics: {meta['topics']}")
    # machine-checkable claims read out of the document itself. Without these
    # an uploaded source carries no assert.* keys, and EvidenceStore's
    # contradiction gate has nothing to group on: the trap we advertise could
    # only ever fire on our own sample pack. Extraction is deliberately
    # conservative (see trustops.assertions) because a wrong assertion invents
    # a contradiction and quarantines a good document.
    for key, value in sorted(extract_assertions(body).items()):
        lines.append(f"assert.{key}: {value}")
    lines += ["---", "", body, ""]
    text = "\n".join(lines)

    # closed loop: the exact reader the pipeline uses must accept this file
    src = _parse_probe(text, source_id, tenant)
    if not src.body.strip():
        raise ExtractError("Document body is empty after synthesis.")
    return source_id, sha, text


def _parse_probe(text: str, source_id: str, tenant: str):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / f"{source_id}.md"
        p.write_text(text, encoding="utf-8")
        try:
            return parse_source(p, tenant)
        except (KeyError, ValueError) as exc:
            raise ExtractError(f"Internal synthesis error: {exc}") from exc


def persist(slug: str, source_id: str, text: str) -> Path:
    dest_dir = config.evidence_root(slug) / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{source_id}.md"
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(dest)
    return dest
