"""Assertion extraction evals.

The contradiction gate groups approved sources by `assert.*` frontmatter keys.
Uploaded documents used to carry none, so the trap the landing page advertises
could only ever fire on our own sample pack. These tests cover the extractors,
the unit normalization, the conservatism that keeps false contradictions out,
and the end-to-end path: two uploads with different deletion windows must
produce a contradiction the existing gate catches.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from trustops.assertions import extract_assertions
from trustops.evidence import EvidenceStore, parse_source
from trustops.server import extract

TODAY = date(2026, 8, 16)

META = {
    "title": "Data Retention Policy", "type": "policy", "version": "1.0",
    "owner": "privacy@example.com", "effective_date": "2026-01-01",
    "expiry_date": "2027-01-01", "topics": "retention, deletion", "attested": "on",
}


# --- extraction --------------------------------------------------------------
@pytest.mark.parametrize("text,key,value", [
    ("Upon termination, all customer content is deleted from production systems "
     "within 90 days.", "customer_data_deletion_days", "90"),
    ("Customer data is retained for 12 months after the contract ends.",
     "customer_data_deletion_days", "365"),
    ("Customer personal data is erased no later than 30 days after a deletion "
     "request.", "customer_data_deletion_days", "30"),
    ("Confirmed incidents affecting customer data trigger customer notification "
     "within 72 hours of confirmation.", "breach_notification_hours", "72"),
    ("We will notify the customer of a personal data breach no later than 1 day "
     "after confirmation.", "breach_notification_hours", "24"),
    ("Data at rest is encrypted with AES-256 across databases and backups.",
     "encryption_algorithm", "AES-256"),
    ("All volumes use 256-bit AES encryption.", "encryption_algorithm", "AES-256"),
    ("Data in transit is protected with TLS 1.2 or higher on all external "
     "connections.", "minimum_tls_version", "1.2"),
    ("The minimum TLS version accepted by our edge is TLS 1.3.",
     "minimum_tls_version", "1.3"),
    ("All workforce access to production systems requires multi-factor "
     "authentication.", "mfa_required", "yes"),
    ("Passwords must be at least 14 characters.", "password_min_length", "14"),
])
def test_extracts_unambiguous_claims(text, key, value):
    assert extract_assertions(text).get(key) == value


# --- unit normalization ------------------------------------------------------
def test_twelve_months_equals_three_hundred_sixty_five_days():
    a = extract_assertions("Customer data is retained for 12 months.")
    b = extract_assertions("Customer data is retained for 365 days.")
    c = extract_assertions("Customer data is retained for 1 year.")
    assert a["customer_data_deletion_days"] == b["customer_data_deletion_days"]
    assert b["customer_data_deletion_days"] == c["customer_data_deletion_days"] == "365"


def test_notification_days_normalize_to_hours():
    a = extract_assertions("Customers are notified of a breach within 3 days.")
    b = extract_assertions("Customers are notified of a breach within 72 hours.")
    assert a["breach_notification_hours"] == b["breach_notification_hours"] == "72"


def test_business_days_are_not_guessed():
    """A business-day window needs a holiday calendar we do not have."""
    out = extract_assertions("Customer data is deleted within 10 business days.")
    assert "customer_data_deletion_days" not in out


# --- conservatism: a wrong assertion is worse than none ----------------------
@pytest.mark.parametrize("text", [
    # a rolling schedule is a process description, not a commitment
    "Backup archives are retained on a 12-month rolling schedule.",
    # log retention is not a customer deletion commitment
    "Audit logs are retained for 365 days in the SIEM.",
    # deprecation notices must never become a minimum
    "TLS 1.0 and TLS 1.1 are disabled on all endpoints.",
    # a bare version mention is not a stated minimum
    "Our load balancers currently negotiate TLS 1.3 with most clients.",
    # roadmap language is not a control in operation
    "We plan to delete customer data within 30 days from next quarter.",
    # scoped exceptions must not become policy-wide negatives
    "MFA is not required for the read-only status page.",
    # a duration with no subject at all
    "Tickets are closed within 5 days.",
])
def test_does_not_extract_ambiguous_or_negated_claims(text):
    assert extract_assertions(text) == {}


def test_document_arguing_with_itself_yields_nothing():
    text = ("Customer content is deleted within 90 days of termination. "
            "Customer records are purged within 30 days of termination.")
    assert "customer_data_deletion_days" not in extract_assertions(text)


def test_mfa_is_only_ever_asserted_positively():
    assert extract_assertions("MFA is mandatory for all administrators.") == \
        {"mfa_required": "yes"}
    assert "mfa_required" not in extract_assertions(
        "Multi-factor authentication is not enforced for service accounts.")


def test_implausible_values_rejected():
    assert extract_assertions(
        "Customer data is retained for 9999 years.") == {}


# --- synthesize() carries the assertions into frontmatter -------------------
def _persisted(tmp_path: Path, body: str, title: str, tenant_dir: Path) -> str:
    meta = extract.validate_meta({**META, "title": title})
    sid, _sha, text = extract.synthesize(meta, body, "acme")
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / f"{sid}.md").write_text(text, encoding="utf-8")
    return sid


def test_synthesize_writes_assert_lines(tmp_path):
    body = ("Customer content is deleted from production systems within 90 days "
            "of termination.\n\nData at rest is encrypted with AES-256.")
    meta = extract.validate_meta(META)
    sid, _sha, text = extract.synthesize(meta, body, "acme")
    assert "assert.customer_data_deletion_days: 90" in text
    assert "assert.encryption_algorithm: AES-256" in text

    p = tmp_path / f"{sid}.md"
    p.write_text(text, encoding="utf-8")
    src = parse_source(p, "acme")
    assert src.assertions["customer_data_deletion_days"] == "90"
    assert src.assertions["encryption_algorithm"] == "AES-256"
    assert "assert.customer_data_deletion_days" not in src.body


def test_document_without_crisp_claims_gets_no_assertions(tmp_path):
    body = ("Acme maintains an information security management system with "
            "documented roles and an annual management review.")
    meta = extract.validate_meta(META)
    _sid, _sha, text = extract.synthesize(meta, body, "acme")
    assert "assert." not in text


# --- end to end: two uploads contradict, and the existing gate catches it ----
def test_two_uploads_with_different_windows_contradict(tmp_path):
    root = tmp_path / "evidence"
    tenant = root / "acme"
    a = _persisted(tmp_path,
                   "Upon termination, all customer content is deleted from "
                   "production systems within 90 days.",
                   "Retention Policy A", tenant)
    b = _persisted(tmp_path,
                   "Customer content is retained for 12 months following "
                   "termination and then deleted.",
                   "Retention Policy B", tenant)
    store = EvidenceStore("acme", root)
    conflicts = store.contradictions(TODAY)
    assert "customer_data_deletion_days" in conflicts
    values = {s.assertions["customer_data_deletion_days"]
              for s in conflicts["customer_data_deletion_days"]}
    assert values == {"90", "365"}
    assert store.contradicted_source_ids(TODAY) == {a, b}


def test_agreeing_uploads_do_not_contradict(tmp_path):
    root = tmp_path / "evidence"
    tenant = root / "acme"
    _persisted(tmp_path,
               "Customer content is retained for 12 months after termination.",
               "Retention Policy C", tenant)
    _persisted(tmp_path,
               "Customer data is deleted within 365 days of termination.",
               "Retention Policy D", tenant)
    store = EvidenceStore("acme", root)
    assert store.contradictions(TODAY) == {}


def test_unattested_uploads_cannot_contradict(tmp_path):
    """Contradiction is a property of APPROVED sources only."""
    root = tmp_path / "evidence"
    tenant = root / "acme"
    tenant.mkdir(parents=True)
    for title, body in (
        ("Draft A", "Customer content is deleted within 90 days of termination."),
        ("Draft B", "Customer content is deleted within 365 days of termination."),
    ):
        meta = extract.validate_meta({**META, "title": title, "attested": ""})
        sid, _sha, text = extract.synthesize(meta, body, "acme")
        (tenant / f"{sid}.md").write_text(text, encoding="utf-8")
    store = EvidenceStore("acme", root)
    assert store.contradictions(TODAY) == {}


# --- PDF chunking: a chunk must be a paragraph, not a page ------------------
def test_pdf_page_becomes_paragraphs_not_one_chunk():
    page = ("DATA RETENTION POLICY\n"
            "Customer content is retained only for the duration of the\n"
            "subscription. Upon contract termination all customer content is\n"
            "deleted from production systems within 90 days.\n"
            "Deletion covers primary datastores and object storage. Media\n"
            "sanitization follows NIST SP 800-88 guidelines.\n"
            "- Backups are encrypted with AES-256.\n"
            "- Keys are rotated annually.\n")
    out = extract._paragraphize_page(page)
    paras = [p for p in out.split("\n\n") if p.strip()]
    assert len(paras) > 1, "a page must not collapse into a single chunk"
    assert any("within 90 days" in p for p in paras)
    # wrapped display lines are rejoined into flowing prose
    assert not any("\n" in p for p in paras)
    # bullets survive as their own paragraphs
    assert any(p.startswith("- Backups") for p in paras)


def test_paragraphize_preserves_genuine_blank_line_breaks():
    page = "First paragraph of the policy.\n\nSecond paragraph of the policy."
    paras = extract._paragraphize_page(page).split("\n\n")
    assert paras == ["First paragraph of the policy.",
                     "Second paragraph of the policy."]


def _multiline_pdf(lines: list[str]) -> bytes:
    """A real PDF whose page extracts as several wrapped display lines."""
    import io
    parts, y = [], 700
    for ln in lines:
        parts.append(f"BT /F1 12 Tf 50 {y} Td ({ln}) Tj ET")
        y -= 18
    stream = " ".join(parts).encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(b"trailer\n<< /Size " + str(len(objs) + 1).encode() +
              b" /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF")
    return out.getvalue()


def test_real_pdf_page_does_not_become_one_chunk():
    """The regression: extract.py joined pages with a blank line and nothing
    else, and evidence.chunks() splits on blank lines, so a PDF page was a
    chunk."""
    text = extract.extract_text("policy.pdf", _multiline_pdf([
        "Customer content is retained only for the duration of the",
        "subscription. Upon contract termination all customer content is",
        "deleted from production systems within 90 days.",
        "Deletion covers primary datastores and object storage. Media",
        "sanitization follows NIST SP 800-88 guidelines.",
    ]))
    paras = [p for p in text.split("\n\n") if p.strip()]
    assert len(paras) > 1, "the page collapsed back into a single chunk"
    assert any("within 90 days" in p for p in paras)
    assert extract_assertions(text)["customer_data_deletion_days"] == "90"


def test_extracted_pdf_chunks_are_paragraph_sized(tmp_path):
    """The whole point: evidence.chunks() splits on blank lines, so what the
    paragraphizer emits is literally the retrieval and citation unit."""
    page = ("Customer content is retained only for the duration of the\n"
            "subscription. Upon contract termination all customer content is\n"
            "deleted from production systems within 90 days.\n"
            "Data at rest is encrypted with AES-256 across databases, object\n"
            "storage and backups. Keys are rotated annually.\n")
    body = extract._paragraphize_page(page)
    meta = extract.validate_meta({**META, "title": "PDF Sourced Policy"})
    sid, _sha, text = extract.synthesize(meta, body, "acme")
    root = tmp_path / "evidence"
    (root / "acme").mkdir(parents=True)
    (root / "acme" / f"{sid}.md").write_text(text, encoding="utf-8")
    chunks = EvidenceStore("acme", root).chunks()
    assert len(chunks) > 1, "one chunk per page defeats retrieval and provenance"
    assert all(len(c.text) < 1200 for c in chunks)


# --- regression: the extractor must not manufacture false contradictions -----
# A re-audit found that the extractor had no notion of WHOSE obligation a
# sentence states. A GDPR Article 33 quotation, which is boilerplate in
# essentially every incident response plan, was extracted as a 72-hour
# notification commitment and collided with the vendor's own 24-hour promise.
# The product then quarantined both documents and told the customer their
# correct policies contradicted each other, naming their document owners.
# That is worse than the gate being inert, so these cases are pinned.

NOT_OUR_COMMITMENT = [
    ("statutory quotation",
     "Under GDPR Article 33, the controller must notify the supervisory "
     "authority of a personal data breach within 72 hours of becoming aware."),
    ("subprocessor obligation",
     "Our subprocessors are contractually obliged to delete customer data "
     "within 90 days of contract end."),
    ("inbound obligation on the customer",
     "The customer shall notify TrustOps of any suspected incident within 24 hours."),
    ("vendor obligation",
     "Vendors must notify us of any breach within 4 hours."),
    ("legacy cipher mention",
     "Supported ciphers include AES-128 for legacy integrations."),
    ("non-production scope",
     "Guest wifi passphrases must be at least 8 characters."),
]


@pytest.mark.parametrize("label,sentence", NOT_OUR_COMMITMENT,
                         ids=[c[0] for c in NOT_OUR_COMMITMENT])
def test_does_not_extract_other_parties_obligations(label, sentence):
    assert extract_assertions(sentence) == {}, (
        f"{label}: extracted an assertion from a sentence that is not our "
        f"commitment; this manufactures a false contradiction")


def test_statutory_quote_does_not_contradict_our_own_commitment():
    """The exact pair that reproduced the failure end to end."""
    ir_plan = ("Under GDPR Article 33, the controller must notify the supervisory "
               "authority of a personal data breach within 72 hours.")
    our_policy = ("We will notify affected customers of a confirmed security "
                  "breach within 24 hours of confirmation.")
    a, b = extract_assertions(ir_plan), extract_assertions(our_policy)
    assert a == {}, "statutory quotation must not become an assertion"
    assert b == {"breach_notification_hours": "24"}
    # no shared key means contradictions() has nothing to flag
    assert not (set(a) & set(b))


def test_real_commitments_still_extract():
    """The guard must not be so broad that it silences genuine claims."""
    assert extract_assertions(
        "Customer data is deleted within 90 days of contract termination."
    ) == {"customer_data_deletion_days": "90"}
    assert extract_assertions(
        "All customer data at rest is encrypted using AES-256."
    ) == {"encryption_algorithm": "AES-256"}
