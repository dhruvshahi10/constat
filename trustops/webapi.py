"""Shared configuration for the serverless functions.

The functions run the same engine as the CLI and the local console — same
retrieval, same gates, same refusal logic. Nothing about safety is re-implemented
for the web; if it were, the website would be a different product from the one
the eval suite tests.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data" / "evidence"

# Workspaces the public demo is allowed to touch. `globex` is the isolation
# decoy and is deliberately not exposed: it exists to be unreachable.
PUBLIC_TENANTS = ("acme", "northwind", "pramana")

MAX_QUESTION_CHARS = 600


def public_tenants() -> list[str]:
    return [t for t in PUBLIC_TENANTS if (EVIDENCE / t).is_dir()]


MAX_BODY_BYTES = 8_192          # a question is 600 chars; anything larger is not a question

# Best-effort per-instance rate limit. Serverless instances are reused but not
# shared, so this bounds a single client hammering one instance; it is not a
# distributed limiter and is not claimed to be one. Its job is to stop casual
# abuse of a public demo, and to make the cost of scraping the corpus tedious.
RATE_WINDOW_SECONDS = 60
RATE_MAX_REQUESTS = 20
_HITS: dict[str, deque] = {}


class RateLimited(RuntimeError):
    pass


def client_ip(headers) -> str:
    forwarded = headers.get("x-forwarded-for", "") or ""
    return (forwarded.split(",")[0].strip() or headers.get("x-real-ip", "") or "unknown")[:64]


def enforce_rate_limit(ip: str, now: float | None = None) -> None:
    now = now if now is not None else time.monotonic()
    hits = _HITS.setdefault(ip, deque())
    while hits and now - hits[0] > RATE_WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= RATE_MAX_REQUESTS:
        raise RateLimited(
            f"rate limit: more than {RATE_MAX_REQUESTS} requests in "
            f"{RATE_WINDOW_SECONDS}s. Run it locally for unlimited use.")
    hits.append(now)
    if len(_HITS) > 4096:      # bound the table itself
        for key in [k for k, v in _HITS.items() if not v][:1024]:
            _HITS.pop(key, None)


def read_body(handler) -> dict:
    """Read a JSON body with a hard size cap, before any parsing."""
    length = int(handler.headers.get("Content-Length", 0) or 0)
    if length > MAX_BODY_BYTES:
        raise ValueError(f"request body exceeds {MAX_BODY_BYTES} bytes")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    try:
        body = __import__("json").loads(raw)
    except ValueError as exc:
        raise ValueError("request body is not valid JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("request body must be a JSON object")
    return body


def safe_error(exc: BaseException) -> tuple[dict, int]:
    """Return an opaque error to the caller and the detail to the server log.

    An exception message can carry a filesystem path, a tenant name or a
    library internal. On a product whose whole argument is that it does not
    leak, echoing that to an anonymous caller would be an unforced error. The
    reference id ties the caller's report to the log line."""
    reference = uuid.uuid4().hex[:12]
    print(f"[error {reference}] {type(exc).__name__}: {exc}", file=sys.stderr)
    if os.environ.get("PRAMANA_DEBUG_ERRORS") == "1":
        return {"error": f"{type(exc).__name__}: {exc}", "reference": reference}, 500
    return {"error": "The engine failed on this request and released nothing. "
                     "Quote the reference if you report it.",
            "reference": reference}, 500
