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


def test_queue_items_carry_customer_and_ranking_fields(client):
    f = ROOT / "data/questionnaires/acme_security_questionnaire.xlsx"
    with f.open("rb") as fh:
        qid = client.post("/v1/questionnaires", headers=H, data={"customer": "Acme Corp"},
                          files={"file": (f.name, fh, "application/octet-stream")}).json()["id"]
    _wait_done(client, qid)
    q = client.get("/v1/review/queue", headers=H).json()
    assert q["count"] > 0
    first = q["items"][0]
    assert first["customer"] == "Acme Corp" and "value_rank" in first and "age_days" in first and "score" in first
    assert first["verdict"]["outcome"] in ("ANSWER", "HOLD_HUMAN")
    review = [i for i in q["items"] if i["state"] == "REVIEW"][0]
    a = client.post(f"/v1/review/{review['id']}/approve", headers=H)
    assert a.status_code == 200 and a.json()["state"] == "APPROVED"
    # an approved answer stays in the queue until it is sent, so the reviewer can send it from there
    assert review["id"] in {i["id"] for i in client.get("/v1/review/queue", headers=H).json()["items"]}
    s = client.post(f"/v1/review/{review['id']}/send", headers=H)
    assert s.status_code == 200 and s.json()["state"] == "SENT"
    assert review["id"] not in {i["id"] for i in client.get("/v1/review/queue", headers=H).json()["items"]}
    m = client.get("/v1/metrics", headers=H).json()
    assert m["claim_fresh_share"] is not None and "cost_per_100_usd" in m


def test_customer_export_hides_internals_and_neutralises_formulas(client, tmp_path):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(["ID", "Domain", "Question", "Response", "Notes"])
    ws.append(["1", "IAM", "Is MFA enforced for all workforce access to production and corporate systems?", "", ""])
    ws.append(["2", "Legal", "Will you indemnify us without limit?", "", ""])
    f = tmp_path / "cust.xlsx"; wb.save(f)
    with f.open("rb") as fh:
        qid = client.post("/v1/questionnaires", headers=H, data={"customer": "Cust"},
                          files={"file": (f.name, fh, "application/octet-stream")}).json()["id"]
    _wait_done(client, qid)
    review = client.get(f"/v1/questionnaires/{qid}/items?state=REVIEW", headers=H).json()["items"]
    client.post(f"/v1/review/{review[0]['id']}/approve", headers=H)
    client.post(f"/v1/review/{review[0]['id']}/send", headers=H)
    import io
    from openpyxl import load_workbook
    cust = load_workbook(io.BytesIO(client.get(f"/v1/questionnaires/{qid}/export", headers=H).content)).active
    assert cust.cell(row=2, column=4).value.startswith("Multi-factor") and cust.cell(row=2, column=5).value in ("", None)
    assert cust.cell(row=3, column=4).value in ("", None) and "LEGAL" not in str(cust.cell(row=3, column=5).value)
    internal = load_workbook(io.BytesIO(client.get(f"/v1/questionnaires/{qid}/export?internal=1", headers=H).content)).active
    assert "LEGAL" in str(internal.cell(row=3, column=5).value)
    from api.routers.questionnaires import _cell_safe
    assert _cell_safe("=HYPERLINK(1)") == "'=HYPERLINK(1)" and _cell_safe("Yes.") == "Yes."


def test_oversized_upload_is_refused_early(client):
    big = b"x" * (6 * 1024 * 1024 + 10)
    r = client.post("/v1/questionnaires", headers=H, files={"file": ("big.csv", big, "text/csv")})
    assert r.status_code == 413
