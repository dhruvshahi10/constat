"""Vanta sync, Slack payloads and signatures, webhooks, the App Framework
wrapper run locally, and the Atlan setup plan."""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constat.claims import Claim, FileClaimStore
from constat.integrations import slack
from constat.integrations.vanta import TestResult, parse_tests, sync

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 28)


@pytest.fixture()
def store(tmp_path):
    spec = json.loads((ROOT / "evals/golden/claims_acme.json").read_text())
    s = FileClaimStore(tmp_path / "claims")
    s.bootstrap([Claim.from_dict(c) for c in spec["claims"]], approver="seed", today=TODAY)
    return s


def test_vanta_sync_proposes_stale_never_deprecates_and_records_passing(store):
    results = [TestResult("okta-mfa-enforced", "failing", TODAY), TestResult("tls-minimum-version", "passing", TODAY),
               TestResult("rds-encryption-at-rest", "muted")]
    rep = sync(store, results, TODAY)
    assert [d.claim_id for d in rep.stale_proposed] == ["iam.mfa"]
    d = rep.stale_proposed[0]
    assert d.owner == "lena.hoff@acme.example" and d.deadline == TODAY + timedelta(days=7) and d.proposal_id
    assert store.get("iam.mfa").status.value == "verified", "a proposal, not a change, until the owner decides"
    pending = store.pending()[0]
    assert pending.claim.valid_until == TODAY - timedelta(days=1) and "Not deprecated" in pending.claim.notes
    assert [d.claim_id for d in rep.muted] == ["crypto.at_rest"]
    assert {d.test_id for d in rep.missing} >= {"github-branch-protection", "quarterly-access-review"}
    assert "crypto.in_transit:tls-minimum-version" in rep.touched
    ref = [e for e in store.get("crypto.in_transit").evidence_refs if e.kind == "vanta_test"][0]
    assert ref.checked_on == TODAY
    # idempotent: a second sync opens no second proposal for the same failing test
    rep2 = sync(store, results, TODAY)
    assert all(d.proposal_id is None for d in rep2.stale_proposed)


def test_parse_tests_accepts_common_shapes():
    assert parse_tests({"results": {"data": [{"testId": "a", "status": "FAILING", "latestFlipTime": "2026-10-01T00:00:00Z"}]}})[0].status == "failing"
    assert parse_tests([{"id": "b", "outcome": "pass"}])[0].status == "passing"
    assert parse_tests({"data": [{"id": "c", "status": "deactivated"}]})[0].status == "muted"


def test_slack_payloads_and_signature():
    p = slack.questionnaire_summary("GitLab", "Q1", {"REVIEW": 3, "QUARANTINED": 1}, link="https://c.example")
    assert "quarantined" in p["blocks"][1]["text"]["text"].lower() and "inbox/Q1" in p["blocks"][2]["elements"][0]["text"]
    e = slack.escalation("tom@acme.example", "Northwind", [{"question": "Q?", "difficulty": "novel", "age_days": 4.2}])
    assert "Escalation to tom@acme.example" in e["text"]
    secret, body, ts = "s3cr3t", b'{"text":"hi"}', str(int(time.time()))
    sig = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    assert slack.verify_signature(secret, ts, body, sig)
    assert not slack.verify_signature(secret, ts, body + b"x", sig)
    assert not slack.verify_signature(secret, str(int(time.time()) - 1000), body, sig)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSTAT_ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("CLAIM_STORE_PATH", str(tmp_path / "claims"))
    monkeypatch.setenv("VANTA_WEBHOOK_SECRET", "vanta-secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "slack-secret")
    from api import deps
    deps.reset()
    from api.main import create_app
    from fastapi.testclient import TestClient
    spec = json.loads((ROOT / "evals/golden/claims_acme.json").read_text())
    FileClaimStore(tmp_path / "claims").bootstrap([Claim.from_dict(c) for c in spec["claims"]], approver="seed", today=TODAY)
    yield TestClient(create_app())
    deps.reset()


def test_webhooks_require_valid_signatures(client):
    body = json.dumps({"data": [{"testId": "okta-mfa-enforced", "status": "failing"}]}).encode()
    bad = client.post("/v1/webhooks/vanta", content=body, headers={"x-constat-signature": "sha256=nope"})
    assert bad.status_code == 401
    sig = "sha256=" + hmac.new(b"vanta-secret", body, hashlib.sha256).hexdigest()
    ok = client.post("/v1/webhooks/vanta", content=body, headers={"x-constat-signature": sig})
    assert ok.status_code == 200 and ok.json()["stale_proposed"][0]["claim_id"] == "iam.mfa"

    ts = str(int(time.time()))
    sbody = json.dumps({"type": "url_verification", "challenge": "abc"}).encode()
    ssig = "v0=" + hmac.new(b"slack-secret", f"v0:{ts}:".encode() + sbody, hashlib.sha256).hexdigest()
    r = client.post("/v1/webhooks/slack/intake", content=sbody,
                    headers={"x-slack-request-timestamp": ts, "x-slack-signature": ssig})
    assert r.status_code == 200 and r.json()["challenge"] == "abc"
    assert client.post("/v1/webhooks/slack/intake", content=sbody,
                       headers={"x-slack-request-timestamp": ts, "x-slack-signature": "v0=bad"}).status_code == 401


def test_app_framework_wrapper_runs_locally(tmp_path, monkeypatch, store):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'side.db'}")
    monkeypatch.setenv("CLAIM_STORE_PATH", str(store.root))
    monkeypatch.setenv("CONSTAT_TMP", str(tmp_path / "tmp"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    sys.path.insert(0, str(ROOT / "apps" / "atlan-app"))
    import importlib
    app = importlib.import_module("app")
    out = app.run_locally(app.ConstatInput(questionnaire_path=str(ROOT / "data/questionnaires/acme_security_questionnaire.xlsx"),
                                           customer="Acme", tenant="acme"))
    assert sum(out.counts.values()) == 24 and out.notified is False and out.questionnaire_id


def test_atlan_setup_plan_is_complete_and_dry_run_works():
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib
    setup = importlib.import_module("atlan_setup")
    spec = json.loads((ROOT / "evals/golden/claims_acme.json").read_text())
    p = setup.plan([Claim.from_dict(c) for c in spec["claims"]], "Security Claims")
    assert len(p["terms"]) == len(spec["claims"]) and p["custom_metadata_set"]["name"] == "Claim"
    names = {a["name"] for a in p["custom_metadata_set"]["attributes"]}
    assert {"exceptions", "audience", "valid_until", "version_hash"} <= names
    assert p["terms"][0]["certificate_status"] in ("VERIFIED", "DRAFT", "DEPRECATED")
