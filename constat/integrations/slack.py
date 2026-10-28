"""Slack: notifications out, signed intake in. Block Kit payloads are pure
functions so they can be tested without a workspace; `post` is a thin urllib
call to an incoming webhook; `verify_signature` implements Slack's v0 signing
scheme for inbound requests."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}}


def _context(text: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text[:2900]}]}


def questionnaire_summary(customer: str, questionnaire_id: str, counts: dict, link: str = "") -> dict:
    total = sum(counts.values())
    rows = ", ".join(f"{k.lower()} {v}" for k, v in sorted(counts.items()))
    text = f"*{customer}*: {total} questions processed. {rows}."
    blocks = [_section(text)]
    if counts.get("QUARANTINED"):
        blocks.append(_section(f":rotating_light: {counts['QUARANTINED']} item(s) quarantined as suspected injection. "
                               f"Tell the customer before answering anything else."))
    if link:
        blocks.append(_context(f"<{link.rstrip('/')}/inbox/{questionnaire_id}|Open in Constat>"))
    return {"text": text, "blocks": blocks}


def routed_question(owner: str, question: str, route: str, deadline: str | None, link: str = "") -> dict:
    text = f"*Question for {owner}* ({route}){' by ' + deadline if deadline else ''}:\n> {question[:600]}"
    blocks = [_section(text), _context("Answer once; it becomes a claim with you as owner.")]
    if link:
        blocks.append(_context(f"<{link}|Open>"))
    return {"text": text, "blocks": blocks}


def quarantine_alert(customer: str, questionnaire_id: str, reasons: list[str], link: str = "") -> dict:
    text = f":rotating_light: *Quarantine* on {customer}'s questionnaire: " + "; ".join(reasons)[:800]
    blocks = [_section(text), _context("Account team: the customer is told we set those items aside; "
                                       "it may be their red team or an altered template.")]
    if link:
        blocks.append(_context(f"<{link.rstrip('/')}/inbox/{questionnaire_id}|Open quarantine>"))
    return {"text": text, "blocks": blocks}


def ae_status(customer: str, held: int, oldest_days: float, status_date: str, degraded: bool) -> dict:
    mode = "The reviewer is unavailable; approved answers continue, new or changed ones are held." if degraded \
        else "Review is running normally."
    text = (f"*{customer}* status {status_date}: {held} question(s) held, oldest {oldest_days} days. {mode}")
    return {"text": text, "blocks": [_section(text)]}


def escalation(backup: str, customer: str, items: list[dict], link: str = "") -> dict:
    lines = "\n".join(f"- {i['question'][:140]} ({i['difficulty']}, {i['age_days']} d)" for i in items[:10])
    text = f"*Escalation to {backup}*: {len(items)} deal-blocking question(s) for {customer}.\n{lines}"
    blocks = [_section(text), _context("One page: what is held, why, and what a decision unblocks.")]
    if link:
        blocks.append(_context(f"<{link}|Open the queue>"))
    return {"text": text, "blocks": blocks}


def freshness_digest(by_owner: dict[str, dict[str, list[str]]], as_of: str) -> dict:
    parts = []
    for owner, b in sorted(by_owner.items()):
        bits = [f"{len(v)} {k}" for k, v in b.items() if v]
        parts.append(f"*{owner}*: " + ", ".join(bits))
    text = f"Claim freshness {as_of}:\n" + ("\n".join(parts) if parts else "nothing expiring")
    return {"text": text, "blocks": [_section(text)]}


def post(webhook_url: str, payload: dict, timeout: float = 10.0) -> bool:
    req = urllib.request.Request(webhook_url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, TimeoutError):
        return False


def verify_signature(signing_secret: str, timestamp: str, body: bytes, signature: str, now: float | None = None) -> bool:
    """Slack request signing, version v0. Rejects replays older than five minutes."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs((now or time.time()) - ts) > 300:
        return False
    base = b"v0:" + str(ts).encode() + b":" + body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")
