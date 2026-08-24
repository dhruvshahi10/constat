"""POST /api/ask — one question through the full gate path.

Deterministic drafter only. That is a product decision, not a limitation: the
hosted demo must be reproducible, must not send a visitor's text to a
third-party model, and must not depend on anyone's API quota staying funded.
The gates are identical either way — swapping the drafter changes fluency, not
safety posture — and dated live-model runs are published as artifacts instead.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Vercel invokes this file directly; put the project root on the path so the
# engine package imports before anything else is loaded.
_ROOT = str(_Path(__file__).resolve().parents[1])
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import json
from datetime import date
from http.server import BaseHTTPRequestHandler

from trustops.webapi import (EVIDENCE, MAX_QUESTION_CHARS, RateLimited,
                             client_ip, enforce_rate_limit, public_tenants,
                             read_body, safe_error)

from trustops.drafter import MockDrafter
from trustops.evidence import EvidenceStore
from trustops.gates import post_gate, pre_gate
from trustops.models import Draft, Question
from trustops.retrieve import Retriever
from trustops.tenants import foreign_parties


def verdict_of(d: Draft) -> str:
    if d.route == "LEGAL":
        return "ROUTED · LEGAL"
    if d.abstained and any(f.startswith("CONTRADICTION") for f in d.gate_flags):
        return "CONTRADICTION · ROUTED TO OWNERS"
    if d.abstained:
        return "ABSTAINED · ROUTED TO " + (d.route or "SME")
    if d.requires_human:
        return "CITED · AWAITING HUMAN REVIEW"
    return "CITED · GATE-CLEAN"


def answer(question_text: str, tenant: str) -> dict:
    allowed = public_tenants()
    if tenant not in allowed:
        raise PermissionError(f"unknown workspace '{tenant}' (available: {', '.join(allowed)})")
    text = question_text.strip()
    if not text:
        raise ValueError("question is empty")
    if len(text) > MAX_QUESTION_CHARS:
        raise ValueError(f"question exceeds {MAX_QUESTION_CHARS} characters")

    store = EvidenceStore(tenant, EVIDENCE)
    retriever = Retriever(store)
    q = Question(question_id="ADHOC", row=0, domain="Ad hoc", text=text)

    others = foreign_parties(EVIDENCE, tenant)
    d = Draft(question_id=q.question_id, answer=None)
    d = pre_gate(q, d, tenant, others)
    if not d.abstained:
        d = MockDrafter(retriever).draft(q, tenant)
        d = pre_gate(q, d, tenant, others)
    else:
        d.drafter, d.model_version, d.prompt_version = "gate", "n/a", "pre-gate-v1"
    d = post_gate(q, d, store, date.today())
    return {"verdict": verdict_of(d), "tenant": tenant, "contract": d.to_contract()}


class handler(BaseHTTPRequestHandler):  # noqa: N801 (Vercel entrypoint contract)
    def _json(self, obj: dict, code: int = 200) -> None:
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        self._json({"tenants": public_tenants(), "drafter": "mock (deterministic)",
                    "max_question_chars": MAX_QUESTION_CHARS})

    def do_POST(self):  # noqa: N802
        try:
            enforce_rate_limit(client_ip(self.headers))
            body = read_body(self)
            self._json(answer(body.get("question", ""), body.get("tenant", "acme")))
        except RateLimited as exc:
            self._json({"error": str(exc)}, code=429)
        except (ValueError, PermissionError) as exc:
            # These carry only messages this module wrote itself — a bad tenant
            # name, an over-length question — so they are safe to return.
            self._json({"error": str(exc)}, code=400)
        except Exception as exc:   # never fabricate an answer, never leak internals
            self._json(*safe_error(exc))
