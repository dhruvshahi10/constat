"""Inbound webhooks, each signed. Vanta: push test results and run the sync.
Slack: a slash command or event that registers a questionnaire for pickup."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from constat.claims import ClaimStore
from constat.integrations import slack
from constat.integrations.vanta import parse_tests, sync
from constat.persist import MetricEvent, Repository, ulid

from ..deps import get_claim_store, get_repo

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


def _bad(msg: str, status: int = 401) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": msg, "code": "WEBHOOK_REJECTED"})


@router.post("/vanta")
async def vanta(request: Request, store: ClaimStore = Depends(get_claim_store), repo: Repository = Depends(get_repo)):
    secret = os.environ.get("VANTA_WEBHOOK_SECRET", "")
    if not secret:
        raise _bad("VANTA_WEBHOOK_SECRET is not configured", 503)
    body = await request.body()
    sig = request.headers.get("x-constat-signature", "")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise _bad("bad signature")
    try:
        results = parse_tests(json.loads(body.decode() or "{}"))
    except json.JSONDecodeError:
        raise _bad("body is not JSON", 422)
    rep = sync(store, results, date.today())
    tenant = os.environ.get("CONSTAT_TENANT", "constat")
    repo.insert("metric_events", MetricEvent(id=ulid(), tenant=tenant, kind="vanta_sync",
                                             value_num=float(len(rep.stale_proposed)),
                                             payload_json={"checked": rep.checked, "muted": len(rep.muted),
                                                           "missing": len(rep.missing)}))
    return rep.to_dict()


@router.post("/slack/intake")
async def slack_intake(request: Request, repo: Repository = Depends(get_repo)):
    secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    if not secret:
        raise _bad("SLACK_SIGNING_SECRET is not configured", 503)
    body = await request.body()
    if not slack.verify_signature(secret, request.headers.get("x-slack-request-timestamp", ""), body,
                                  request.headers.get("x-slack-signature", "")):
        raise _bad("bad signature")
    try:
        payload = json.loads(body.decode() or "{}")
    except json.JSONDecodeError:
        raise _bad("body is not JSON", 422)
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    # a message that names a customer and a file: register it for pickup by the
    # reviewer, who uploads the file through the app. Download from Slack needs a
    # bot token and is deliberately not automated here.
    text = str(payload.get("text") or payload.get("event", {}).get("text") or "")[:500]
    tenant = os.environ.get("CONSTAT_TENANT", "constat")
    repo.insert("metric_events", MetricEvent(id=ulid(), tenant=tenant, kind="slack_intake", value_num=1.0,
                                             payload_json={"text": text, "user": str(payload.get("user_id") or "")}))
    return {"response_type": "ephemeral",
            "text": "Noted. Upload the file in Constat's inbox and it will be drafted within the hour; "
                    "you will get a status here when anything is held."}
