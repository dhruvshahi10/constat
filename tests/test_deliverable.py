"""The client deliverable package.

What is asserted here is what a client is entitled to assume when the folder
lands in their inbox: that it is self-contained, that every link on the cover
page resolves, that the refusals are all present in the work-list with a named
owner, that the audit chain still verifies after the copy, and that a human
review — if one happened — is the state the package reports.
"""
from __future__ import annotations

import json
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trustops.deliverable import Artifact, DeliveryError, GapItem, build, write_index
from trustops.pipeline import AuditLog, run
from trustops.report import write_report
from trustops.review import ReviewSession

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data" / "evidence"
QNR = ROOT / "data" / "questionnaires" / "acme_security_questionnaire.xlsx"
TODAY = date(2026, 8, 8)


class _Hrefs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs += [v for k, v in attrs if k == "href" and v]


def _local_links(page: Path) -> list[str]:
    parser = _Hrefs()
    parser.feed(page.read_text(encoding="utf-8"))
    return [h for h in parser.hrefs
            if urlparse(h).scheme not in ("http", "https", "mailto")]


def _make_run(tmp_path: Path, tenant: str) -> Path:
    out = tmp_path / f"run-{tenant}"
    res = run(QNR, tenant=tenant, evidence_root=EVIDENCE, out_dir=out,
              drafter_kind="mock", today=TODAY)
    write_report(res, TODAY)
    return out


@pytest.fixture(scope="module")
def acme(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("acme")
    return build(_make_run(tmp, "acme"), out_root=tmp / "deliveries")


@pytest.fixture(scope="module")
def northwind(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("northwind")
    return build(_make_run(tmp, "northwind"), out_root=tmp / "deliveries")


# --- the package exists and is self-contained --------------------------------
def test_package_contains_every_promised_artifact(acme):
    out = acme.out_dir
    assert out.name == "2026-08-08-acme", "folder is dated by the engagement, not by today"
    for name in ("index.html", "README.md", "evidence_gaps.md", "contracts.json",
                 "audit_log.jsonl", "run_report.html", "trust_page/index.html"):
        assert (out / name).is_file(), f"{name} missing from the package"
    assert list(out.glob("*__DELIVERED.xlsx")), "the completed workbook is the product"


def test_commitment_register_present_only_when_the_client_has_one(acme, northwind):
    assert (acme.out_dir / "commitment_register" / "index.html").is_file()
    assert (acme.out_dir / "commitment_register" / "commitments.json").is_file()
    # northwind has no data/commitments/northwind.json — nothing is invented for it
    assert not (northwind.out_dir / "commitment_register").exists()


def test_every_cover_page_link_resolves(acme, northwind):
    for pkg in (acme, northwind):
        links = _local_links(pkg.index_path)
        assert links, "the cover page must link the artifacts"
        for href in links:
            target = pkg.out_dir / unquote(urlparse(href).path)
            assert target.is_file(), f"{href} does not resolve in {pkg.out_dir}"
        linked = {unquote(urlparse(h).path) for h in links}
        for art in pkg.artifacts:
            assert art.path in linked, f"{art.path} is described but not linked"


def test_package_is_self_contained(acme):
    """No link escapes the folder — it has to survive being zipped and emailed."""
    for href in _local_links(acme.index_path):
        path = unquote(urlparse(href).path)
        assert not path.startswith(("/", "..")), f"{href} points outside the package"


# --- the numbers a buyer reads first -----------------------------------------
def test_headline_numbers_match_the_contracts(acme):
    contracts = json.loads((acme.out_dir / "contracts.json").read_text(encoding="utf-8"))
    released = [c for c in contracts.values()
                if c["status"] in ("evidence_backed", "partial", "requires_human",
                                   "human_authored")]
    refused = [c for c in contracts.values()
               if c["status"] in ("no_evidence", "routed")]
    s = acme.summary
    assert s["questions"] == len(contracts)
    assert s["refused"] == len(refused)
    assert s["answered_with_citations"] == sum(
        1 for c in released if c["citations"] and c["status"] != "human_authored")
    assert s["open_items"] == len(acme.gaps) == s["refused"]


def test_refusal_is_presented_as_the_control_working(acme):
    cover = acme.index_path.read_text(encoding="utf-8")
    assert "control working" in cover
    assert "refused" in cover.lower()


# --- evidence_gaps.md: the artifact they renew for ---------------------------
def test_every_refusal_is_a_work_item_with_a_named_owner(acme, northwind):
    for pkg in (acme, northwind):
        contracts = json.loads(
            (pkg.out_dir / "contracts.json").read_text(encoding="utf-8"))
        refused = {qid for qid, c in contracts.items()
                   if c["status"] in ("no_evidence", "routed")}
        assert {g.question_id for g in pkg.gaps} == refused
        text = (pkg.out_dir / "evidence_gaps.md").read_text(encoding="utf-8")
        for gap in pkg.gaps:
            assert gap.question_id in text
            assert gap.routed_to, f"{gap.question_id} has nobody to route to"
            assert gap.action, f"{gap.question_id} names no action"
            assert gap.routed_to in text


def test_gaps_are_grouped_by_reason(acme):
    groups = {g.group for g in acme.gaps}
    assert {"contradiction", "stale", "legal"} <= groups
    text = (acme.out_dir / "evidence_gaps.md").read_text(encoding="utf-8")
    assert "## Two approved documents disagree" in text
    assert "## The supporting document has expired" in text
    assert "## Needs legal, not evidence" in text


def test_gaps_name_the_specific_document(acme):
    """A work-list that says 'more evidence needed' is not a work-list."""
    stale = [g for g in acme.gaps if g.group == "stale"]
    assert stale, "the acme corpus has an expired source; it must surface here"
    assert any("POL-RET-002" in d or "RPT-PEN-2024" in d
               for g in stale for d in g.documents)
    contradiction = [g for g in acme.gaps if g.group == "contradiction"]
    assert any("POL-RET-001" in d for g in contradiction for d in g.documents)


def test_certification_refusal_asks_for_the_certificate(acme):
    """T1's client-facing half: the fix is the certificate, not 'more docs'."""
    cert = [g for g in acme.gaps if g.question_id == "A&A-02.1"]
    assert cert, "the ISO 27001 question was refused and must appear"
    assert cert[0].group == "certificate"
    assert "certificate" in cert[0].action.lower()


def test_thin_corpus_produces_a_long_work_list(northwind):
    """A 4-document corpus should be reported as such, not padded."""
    assert len(northwind.gaps) > 10
    assert northwind.summary["refused"] > northwind.summary["answered_with_citations"]
    assert sum(1 for g in northwind.gaps if g.group == "no_evidence") >= 5


# --- integrity ----------------------------------------------------------------
def test_audit_chain_verifies_on_the_copy_that_ships(acme):
    assert acme.summary["audit_chain_valid"] is True
    assert AuditLog.verify_chain(acme.out_dir / "audit_log.jsonl")


def test_tampering_with_the_shipped_log_is_detectable(acme, tmp_path):
    """The copy carries the same property as the original, not a claim of it."""
    copied = tmp_path / "audit_log.jsonl"
    lines = (acme.out_dir / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[1])
    obj["detail"] = {"question_count": 999}
    lines[1] = json.dumps(obj, ensure_ascii=False)
    copied.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not AuditLog.verify_chain(copied)


def test_no_unescaped_client_text_in_the_cover(acme):
    cover = acme.index_path.read_text(encoding="utf-8")
    assert "innerHTML" not in cover
    assert "<script" not in cover.lower()


def test_client_supplied_text_is_escaped_not_rendered(tmp_path):
    """Client names, question text and file names all reach the cover page.

    None of them is trusted: a questionnaire is a file somebody else wrote and
    sent, so everything that crosses into HTML is escaped rather than filtered.
    """
    hostile = '<script>alert("x")</script> & "Co"'
    page = tmp_path / "index.html"
    write_index(
        page, client=hostile, engagement=date(2026, 8, 8),
        summary={"questions": 1, "answered_with_citations": 0, "refused": 1,
                 "open_items": 1, "open_items_by_reason": {"no_evidence": 1},
                 "audit_chain_valid": True, "audit_chain_signed": False},
        artifacts=[Artifact("a b/c&d.html", hostile, hostile)],
        gaps=[GapItem(question_id="Q1", domain=hostile, question=hostile,
                      group="no_evidence", action=hostile)],
        paragraphs=[hostile], generated=date(2026, 8, 25))
    rendered = page.read_text(encoding="utf-8")
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;" in rendered
    assert 'href="a%20b/c%26d.html"' in rendered, "paths are percent-encoded, not raw"


def test_cover_reports_the_chain_honestly_when_unsigned(acme):
    cover = acme.index_path.read_text(encoding="utf-8")
    assert acme.summary["audit_chain_signed"] is False
    assert "not signed" in cover, "an unsigned log must not imply tamper-resistance"


# --- human review is reflected ------------------------------------------------
def test_package_reflects_a_recorded_human_decision(tmp_path):
    run_dir = _make_run(tmp_path, "acme")
    session = ReviewSession(run_dir)
    refused = next(q.question_id for q in session.questions
                   if not session.drafts[q.question_id].status.released)
    session.decide(refused, "edit", actor="Priya Nair <priya@acme.example>",
                   answer="Customer data is deleted within 30 days.",
                   note="answering from the signed DPA")
    session.export()

    pkg = build(run_dir, out_root=tmp_path / "deliveries")
    assert pkg.summary["human_decisions"] == 1
    assert "Priya Nair <priya@acme.example>" in pkg.summary["reviewers"]
    assert pkg.summary["human_authored"] == 1
    assert (pkg.out_dir / "review_decisions.json").is_file()

    # the edited question is no longer an open item; it was answered by a person
    assert refused not in {g.question_id for g in pkg.gaps}
    contracts = json.loads((pkg.out_dir / "contracts.json").read_text(encoding="utf-8"))
    assert contracts[refused]["status"] == "human_authored"
    cover = pkg.index_path.read_text(encoding="utf-8")
    assert "HUMAN AUTHORED" in cover, "a human-written answer is never sold as evidence-backed"
    assert AuditLog.verify_chain(pkg.out_dir / "audit_log.jsonl"), \
        "review events extend the same chain and must still verify in the package"


# --- failure modes ------------------------------------------------------------
def test_unpackageable_run_says_what_to_do(tmp_path):
    empty = tmp_path / "not-a-run"
    empty.mkdir()
    with pytest.raises(DeliveryError) as exc:
        build(empty, out_root=tmp_path / "deliveries")
    assert "manifest.json" in str(exc.value)


def test_missing_workbook_is_refused_rather_than_shipped(tmp_path):
    run_dir = _make_run(tmp_path, "acme")
    for xlsx in run_dir.glob("*__DELIVERED.*"):
        xlsx.unlink()
    with pytest.raises(DeliveryError) as exc:
        build(run_dir, out_root=tmp_path / "deliveries")
    assert "DELIVERED" in str(exc.value)


def test_rebuilding_the_same_run_is_idempotent(tmp_path):
    run_dir = _make_run(tmp_path, "acme")
    first = build(run_dir, out_root=tmp_path / "deliveries")
    before = (first.out_dir / "evidence_gaps.md").read_text(encoding="utf-8")
    second = build(run_dir, out_root=tmp_path / "deliveries")
    assert second.out_dir == first.out_dir
    assert (second.out_dir / "evidence_gaps.md").read_text(encoding="utf-8") == before
