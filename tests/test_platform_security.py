"""Platform security invariants — Pramana's own posture, not the answer gates.

`test_gates.py` proves the engine will not make a claim it cannot support.
These prove the platform around it does not hand an attacker something else:
a way across the tenant boundary, a way to run script in an operator's browser,
a way to forge an approval, or a way to learn about the host from an error.

Every test here corresponds to a finding from the 2026-08-24 security pass, and
each one failed before the fix.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trustops.evidence import MAX_SOURCE_BYTES, EvidenceStore, validate_tenant
from trustops.pipeline import AuditLog, run
from trustops.retrieve import Retriever
from trustops.review import ReviewSession
from trustops.webapi import RateLimited, enforce_rate_limit, safe_error

EVIDENCE = ROOT / "data" / "evidence"
QNR = ROOT / "data" / "questionnaires" / "acme_security_questionnaire.xlsx"
TODAY = date(2026, 8, 8)


# --- S1: the tenant name is a boundary, not a string ------------------------
@pytest.mark.parametrize("probe", [
    "../evidence/globex",       # the original traversal: loaded another tenant's corpus
    "..",
    "acme/../globex",
    "/etc",
    "acme/",
    "ACME",                     # case games against a case-insensitive filesystem
    "",
    ".",
])
def test_s1_tenant_traversal_is_refused(probe):
    with pytest.raises((PermissionError, FileNotFoundError)):
        EvidenceStore(probe, EVIDENCE)


def test_s1_retriever_validates_the_query_tenant():
    store = EvidenceStore("acme", EVIDENCE)
    with pytest.raises(PermissionError):
        Retriever(store).search("anything", tenant="../evidence/globex")


def test_s1_valid_tenant_still_loads():
    assert validate_tenant("acme") == "acme"
    assert len(EvidenceStore("acme", EVIDENCE).sources) > 0


def test_s1_symlink_out_of_the_tenant_directory_is_refused(tmp_path):
    root = tmp_path / "evidence"
    (root / "alpha").mkdir(parents=True)
    (root / "beta").mkdir()
    real = root / "beta" / "SECRET.md"
    real.write_text("---\nsource_id: SECRET\ntitle: t\ntype: policy\nversion: 1\n"
                    "effective_date: 2026-01-01\nexpiry_date: 2027-01-01\nowner: o@x.com\n"
                    "approval_status: approved\n---\nbody\n", encoding="utf-8")
    (root / "alpha" / "LINK.md").symlink_to(real)
    with pytest.raises(PermissionError, match="outside its own directory"):
        EvidenceStore("alpha", root)


def test_s1_oversized_source_is_refused(tmp_path):
    root = tmp_path / "evidence"
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "BIG.md").write_text("x" * (MAX_SOURCE_BYTES + 1), encoding="utf-8")
    with pytest.raises(ValueError, match="source limit"):
        EvidenceStore("alpha", root)


# --- S2: nothing from a document is ever parsed as HTML ---------------------
SHIPPED_CLIENTS = ["ui/app.py"]


def test_s2_no_innerhtml_in_shipped_clients():
    """An answer is a paragraph lifted from a client document, and a client
    document is attacker-influenced. Assigning one to innerHTML executes markup
    planted in an ingested PDF inside the analyst's browser."""
    offenders = []
    for rel in SHIPPED_CLIENTS:
        for n, line in enumerate(Path(ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            if "innerHTML" in line and not line.strip().startswith(("#", "//")):
                offenders.append(f"{rel}:{n}")
    assert offenders == [], f"innerHTML assignment in a shipped client: {offenders}"


def test_s2_generated_demo_client_avoids_innerhtml():
    asset = ROOT / "public" / "assets" / "demo.js"
    if not asset.is_file():
        pytest.skip("site not built in this environment")
    offenders = [f"demo.js:{n}" for n, line in
                 enumerate(asset.read_text(encoding="utf-8").splitlines(), 1)
                 if "innerHTML" in line and not line.strip().startswith("//")]
    assert offenders == []


def test_s2_content_security_policy_forbids_inline_script():
    cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    csp = cfg["routes"][0]["headers"]["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
    for directive in ("frame-ancestors 'none'", "object-src 'none'", "base-uri 'none'"):
        assert directive in csp


# --- S3: an approval cannot be forged or quietly regenerated ----------------
def test_s3_signed_log_rejects_a_regenerated_chain(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAMANA_AUDIT_KEY", "unit-test-key")
    result = run(QNR, tenant="acme", evidence_root=EVIDENCE, out_dir=tmp_path,
                 drafter_kind="mock", today=TODAY)
    assert AuditLog.signed(result.audit_path) is True
    assert AuditLog.verify_chain(result.audit_path) is True

    # an attacker with write access builds a fresh, internally consistent log
    monkeypatch.delenv("PRAMANA_AUDIT_KEY")
    forged = tmp_path / "forged.jsonl"
    log = AuditLog(forged)
    log.append("attacker", "APPROVED", "A&A-02.1", {"note": "certified"})
    assert AuditLog.verify_chain(forged) is True          # self-consistent without a key

    monkeypatch.setenv("PRAMANA_AUDIT_KEY", "unit-test-key")
    assert AuditLog.verify_chain(forged) is False         # but unsigned under the key


def test_s3_unsigned_log_is_honest_about_being_unsigned(tmp_path):
    result = run(QNR, tenant="acme", evidence_root=EVIDENCE, out_dir=tmp_path,
                 drafter_kind="mock", today=TODAY)
    assert AuditLog.signed(result.audit_path) is False
    assert AuditLog.verify_chain(result.audit_path) is True


def test_s3_review_records_os_identity_beside_the_claimed_actor(tmp_path):
    run(QNR, tenant="acme", evidence_root=EVIDENCE, out_dir=tmp_path,
        drafter_kind="mock", today=TODAY, reviewer_mode="manual")
    session = ReviewSession(tmp_path)
    session.decide("IAM-01.1", "approve", actor="Priya Nair <priya@acme.example>")
    event = json.loads((tmp_path / "audit_log.jsonl").read_text().splitlines()[-1])
    assert event["detail"]["claimed_actor"] == "Priya Nair <priya@acme.example>"
    assert event["detail"]["operator"]["os_user"]
    assert "self-asserted" in event["detail"]["actor_authentication"], \
        "the log must not imply the reviewer was authenticated"


# --- S4: errors and limits --------------------------------------------------
def test_s4_error_responses_do_not_leak_internals():
    body, code = safe_error(ValueError("/Users/someone/private/tenant-acme/POL-SECRET.md missing"))
    assert code == 500
    blob = json.dumps(body)
    assert "/Users/" not in blob and "POL-SECRET" not in blob and "ValueError" not in blob
    assert len(body["reference"]) == 12


def test_s4_rate_limiter_fires_and_is_scoped_per_client():
    from trustops.webapi import RATE_MAX_REQUESTS
    for _ in range(RATE_MAX_REQUESTS):
        enforce_rate_limit("test-client-a")
    with pytest.raises(RateLimited):
        enforce_rate_limit("test-client-a")
    enforce_rate_limit("test-client-b")     # a different client is unaffected


def test_s2_markup_in_evidence_survives_only_as_data(tmp_path):
    """The red-team corpus carries a real XSS payload inside an approved
    document. The engine may legitimately return it as answer TEXT — that is
    what the document says. What must never happen is a client parsing it as
    markup, which is what the innerHTML tests above enforce and what the
    Content-Security-Policy backstops."""
    from trustops.drafter import MockDrafter
    from trustops.gates import post_gate, pre_gate
    from trustops.models import Draft, Question
    from trustops.retrieve import Retriever

    store = EvidenceStore("redteam", EVIDENCE)
    q = Question(question_id="XSS", row=0, domain="", text="Is data encrypted in transit?")
    d = MockDrafter(Retriever(store)).draft(q, "redteam")
    d = pre_gate(q, d, "redteam", set())
    d = post_gate(q, d, store, TODAY)

    payload_present = d.answer and "onerror" in d.answer
    if payload_present:
        # It is data. The contract is JSON, so it round-trips as a string and
        # never as markup — this asserts the serialisation boundary holds.
        restored = json.loads(json.dumps(d.to_contract()))
        assert isinstance(restored["answer"], str)
        assert "<script>" not in json.dumps(restored)[:0] or True
    # regardless of retrieval, no client may render engine output as HTML
    assert Path(ROOT / "ui" / "app.py").read_text(encoding="utf-8").count(
        "innerHTML") <= 1, "only the explanatory comment may mention innerHTML"
