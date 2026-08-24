"""POST /api/waitlist — record an early-access request.

Stored in Supabase via its REST endpoint (stdlib urllib, no SDK). If the
backend is not configured or not reachable the endpoint says so plainly and the
page falls back to a mail link. It never reports a signup it did not store —
the whole product is about not claiming more than the evidence supports, and
that applies to its own signup form.
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
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

from trustops.webapi import ROOT  # noqa: F401

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")
TABLE = "waitlist"
MAX_NOTE = 400


def _config() -> tuple[str, str] | None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    return (url, key) if url and key else None


def submit(email: str, note: str, source: str) -> dict:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise ValueError("that does not look like an email address")
    conf = _config()
    if conf is None:
        raise RuntimeError("waitlist backend not configured")
    url, key = conf
    payload = json.dumps({"email": email, "note": (note or "")[:MAX_NOTE],
                          "source": (source or "site")[:60]}).encode()
    req = urllib.request.Request(
        f"{url}/rest/v1/{TABLE}", data=payload, method="POST",
        headers={"Content-Type": "application/json", "apikey": key,
                 "Authorization": f"Bearer {key}", "Prefer": "resolution=merge-duplicates"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 201, 204):
                raise RuntimeError(f"waitlist store returned {resp.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"waitlist store rejected the entry ({exc.code}): {detail}") from exc
    except OSError as exc:
        raise RuntimeError(f"waitlist store unreachable ({type(exc).__name__})") from exc
    return {"stored": True, "email": email}


class handler(BaseHTTPRequestHandler):  # noqa: N801
    def _json(self, obj: dict, code: int = 200) -> None:
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        self._json({"configured": _config() is not None})

    def do_POST(self):  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            self._json(submit(body.get("email", ""), body.get("note", ""),
                              body.get("source", "site")))
        except ValueError as exc:
            self._json({"error": str(exc)}, code=400)
        except RuntimeError as exc:
            self._json({"error": str(exc), "fallback": "mail"}, code=503)
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, code=500)
