"""Upload, process in the background, read items, quarantine, diff, export."""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSTAT_ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'side.db'}")
    monkeypatch.setenv("CLAIM_STORE_PATH", str(tmp_path / "claims"))
    monkeypatch.setenv("CONSTAT_DEV_TOKEN", "dev-secret-token")
    monkeypatch.setenv("CONSTAT_TENANT", "acme")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from api import deps
    deps.reset()
    from api.main import create_app
    from constat.claims import Claim, FileClaimStore
    spec = json.loads((ROOT / "evals/golden/claims_acme.json").read_text())
    FileClaimStore(tmp_path / "claims").bootstrap([Claim.from_dict(c) for c in spec["claims"]],
                                                  approver="seed", today=date(2026, 10, 28))
    with TestClient(create_app()) as c:
        yield c
    deps.reset()


H = {"Authorization": "Bearer dev-secret-token"}


def _wait_done(client, qid, timeout=30):
    for _ in range(timeout * 10):
        q = client.get(f"/v1/questionnaires/{qid}", headers=H).json()
        if q["status"] == "done" or q["status"].startswith("error"):
            return q
        time.sleep(0.1)
    raise AssertionError("questionnaire never finished")


def test_upload_process_items_diff_export(client):
    f = ROOT / "data/questionnaires/gitlab_caiq_v4_subset.xlsx"
    with f.open("rb") as fh:
        r = client.post("/v1/questionnaires", headers=H, data={"customer": "GitLab", "audience": "nda"},
                        files={"file": (f.name, fh, "application/octet-stream")})
    assert r.status_code == 202, r.text
    qid = r.json()["id"]
    assert r.json()["questions"] == 54
    q = _wait_done(client, qid)
    assert q["status"] == "done" and q["total"] == 54 and q["counts"].get("SENT", 0) == 0

    items = client.get(f"/v1/questionnaires/{qid}/items?state=REVIEW", headers=H).json()["items"]
    assert items and all(i["draft_answer"] for i in items)
    one = client.get(f"/v1/questions/{items[0]['id']}", headers=H).json()
    assert one["claim"]["claim_id"] == items[0]["claim_id"] and one["last_approved_answer"] is None
    assert client.get(f"/v1/questions/{items[0]['id']}/diff", headers=H).json()["ops"][0]["op"] == "ins"

    assert client.get(f"/v1/questionnaires/{qid}/quarantine", headers=H).json()["items"] == []
    listed = client.get("/v1/questionnaires", headers=H).json()["questionnaires"]
    assert listed[0]["id"] == qid

    x = client.get(f"/v1/questionnaires/{qid}/export", headers=H)
    assert x.status_code == 200 and x.headers["content-type"].startswith("application/vnd.openxmlformats")
    from openpyxl import load_workbook
    import io
    ws = load_workbook(io.BytesIO(x.content)).active
    assert ws.cell(row=4, column=3).value.startswith("Do you maintain") and ws.cell(row=4, column=5).value


def test_sse_events_reach_done(client):
    f = ROOT / "data/questionnaires/acme_security_questionnaire.xlsx"
    with f.open("rb") as fh:
        qid = client.post("/v1/questionnaires", headers=H, data={"customer": "Acme"},
                          files={"file": (f.name, fh, "application/octet-stream")}).json()["id"]
    _wait_done(client, qid)
    with client.stream("GET", f"/v1/questionnaires/{qid}/events", headers=H) as s:
        body = "".join(s.iter_text())
    assert "event: item.state" in body and "event: questionnaire.done" in body


def test_bad_uploads(client):
    assert client.post("/v1/questionnaires", headers=H, files={"file": ("x.pdf", b"%PDF", "application/pdf")}).status_code == 422
    assert client.post("/v1/questionnaires", headers=H, data={"audience": "secret"},
                       files={"file": ("x.csv", b"ID,Question\n1,Is MFA on?\n", "text/csv")}).status_code == 422
    assert client.get("/v1/questionnaires/nope", headers=H).status_code == 404
