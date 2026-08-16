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


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join(filter(None, (p.extract_text() for p in reader.pages)))
    except ExtractError:
        raise
    except Exception as exc:  # noqa: BLE001 — pypdf raises a zoo of types
        raise ExtractError(f"Could not read this PDF ({type(exc).__name__}). "
                           "Is the file corrupt or password protected?") from exc
    if not text.strip():
        raise ExtractError("No extractable text in this PDF. Scanned documents "
                           "need OCR, which is not supported yet.")
    return text


def _docx_text(data: bytes) -> str:
    try:
        import docx
        d = docx.Document(io.BytesIO(data))
        text = "\n\n".join(p.text for p in d.paragraphs if p.text.strip())
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
