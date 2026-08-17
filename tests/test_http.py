"""HTTP-layer evals: the real server, a real socket, real requests.

Everything below this line was previously untested. The handler is where auth,
rate limits, path handling, body limits and error mapping actually live, so a
suite that only calls the functions underneath it proves very little. These
tests boot the actual ThreadingHTTPServer on an ephemeral port and talk to it
with urllib.
"""
from __future__ import annotations

import io
import json
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from pramana.server import app, config, db

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------

_SAVED = ("DATA", "DB_PATH", "TENANTS", "SIGNUPS_PER_IP_PER_DAY",
          "SIGNUPS_PER_DAY_GLOBAL", "MAX_BODY_BYTES", "MAX_DOCS_PER_TENANT",
          "MAX_TENANT_BYTES")


class _Resp:
    __slots__ = ("status", "headers", "body")

    def __init__(self, status: int, headers, body: bytes):
        self.status, self.headers, self.body = status, headers, body

    def json(self) -> dict:
        return json.loads(self.body.decode() or "{}")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("http")
    saved = {k: getattr(config, k) for k in _SAVED}
    config.DATA = tmp / "data"
    config.DB_PATH = tmp / "data" / "pramana.db"
    config.TENANTS = tmp / "data" / "tenants"
    config.SIGNUPS_PER_IP_PER_DAY = 100
    config.SIGNUPS_PER_DAY_GLOBAL = 10_000
    config.MAX_BODY_BYTES = 4096          # keep the 413 test cheap
    db.init()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True, name="test-httpd")
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        yield base
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)
        for k, v in saved.items():
            setattr(config, k, v)


def call(base: str, method: str, path: str, body: bytes | None = None,
         headers: dict[str, str] | None = None) -> _Resp:
    req = urllib.request.Request(base + path, data=body, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return _Resp(r.status, r.headers, r.read())
    except urllib.error.HTTPError as e:      # 4xx/5xx are results, not failures
        return _Resp(e.code, e.headers, e.read())


def signup(base: str, org: str, *, consent: bool = True,
           xff: str | None = None, email: str | None = None) -> _Resp:
    payload = {"org": org, "email": email or f"a@{org.replace(' ', '')}.com"}
    if consent:
        payload["consent"] = True
    headers = {"Content-Type": "application/json"}
    if xff:
        headers["X-Forwarded-For"] = xff
    return call(base, "POST", "/api/signup", json.dumps(payload).encode(), headers)


def new_workspace(base: str, org: str) -> tuple[str, str]:
    """Returns (slug, token)."""
    r = signup(base, org)
    assert r.status == 200, r.body
    out = r.json()
    return out["slug"], out["workspace"].split("?k=", 1)[1]


# ---------------------------------------------------------------------------
# healthz
# ---------------------------------------------------------------------------
@pytest.fixture()
def live_worker():
    """Stand-in for the run worker; healthz must key off thread liveness."""
    from pramana.server import runqueue
    stop = threading.Event()
    t = threading.Thread(target=stop.wait, daemon=True, name="fake-worker")
    t.start()
    prev = runqueue._worker
    runqueue._worker = t
    yield
    runqueue._worker = prev
    stop.set()
    t.join(timeout=5)


def test_healthz_green_when_worker_alive(server, live_worker):
    r = call(server, "GET", "/healthz")
    assert r.status == 200
    assert r.json() == {"ok": True, "worker": "alive"}


def test_healthz_red_when_worker_dead(server):
    """C1: a health check that cannot go red is decoration."""
    from pramana.server import runqueue
    prev = runqueue._worker
    runqueue._worker = None
    try:
        r = call(server, "GET", "/healthz")
        assert r.status == 503
        assert r.json() == {"ok": False, "worker": "dead"}
    finally:
        runqueue._worker = prev


# ---------------------------------------------------------------------------
# signup
# ---------------------------------------------------------------------------
def test_signup_happy_path(server):
    r = signup(server, "Happy Path Co")
    assert r.status == 200
    out = r.json()
    assert out["slug"] == "happy-path-co"
    assert out["workspace"].startswith("/t/happy-path-co?k=t.happy-path-co.")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE slug=?", (out["slug"],)).fetchone()
    assert row["consent_at"], "consent timestamp must be recorded"
    assert row["token_hash"] not in out["workspace"], "only the hash is stored"


def test_signup_rejected_without_consent(server):
    r = signup(server, "No Consent Co", consent=False)
    assert r.status == 422
    assert r.json()["error"] == "You must accept the Terms and Privacy Notice."
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tenants WHERE slug=?",
                            ("no-consent-co",)).fetchone()[0] == 0


def test_signup_rejects_bad_input(server):
    assert signup(server, "X").status == 422                      # org too short
    assert signup(server, "Bad Email Co", email="nope").status == 422
    r = call(server, "POST", "/api/signup", b"{not json",
             {"Content-Type": "application/json"})
    assert r.status == 422


def test_signup_ip_limit_uses_last_forwarded_hop(server, monkeypatch):
    """C3: proxies APPEND to XFF, so the first value is attacker-controlled."""
    monkeypatch.setattr(config, "SIGNUPS_PER_IP_PER_DAY", 1)
    assert signup(server, "Hop One Co", xff="203.0.113.9").status == 200
    # attacker prepends a fake hop; the real peer is still the last entry
    r = signup(server, "Hop Two Co", xff="10.0.0.1, 203.0.113.9")
    assert r.status == 429, "spoofed leading XFF hop bypassed the signup limit"
    # a genuinely different peer is unaffected
    assert signup(server, "Hop Three Co", xff="198.51.100.7").status == 200


def test_signup_global_backstop(server, monkeypatch):
    """C3 backstop: rotating IPs must still hit a global daily ceiling."""
    monkeypatch.setattr(config, "SIGNUPS_PER_DAY_GLOBAL", 0)
    r = signup(server, "Backstop Co", xff="198.51.100.99")
    assert r.status == 429
    assert "paused for today" in r.json()["error"]


# ---------------------------------------------------------------------------
# auth boundary
# ---------------------------------------------------------------------------
def test_missing_token_rejected(server):
    slug, _ = new_workspace(server, "No Token Co")
    r = call(server, "GET", f"/t/{slug}/api/state")
    assert r.status == 403
    assert "invalid or expired" in r.json()["error"]


def test_cross_tenant_token_rejected(server):
    a_slug, a_token = new_workspace(server, "Tenant A Co")
    b_slug, _ = new_workspace(server, "Tenant B Co")
    r = call(server, "GET", f"/t/{b_slug}/api/state?k={a_token}")
    assert r.status == 403, "tenant A's token opened tenant B's workspace"
    ok = call(server, "GET", f"/t/{a_slug}/api/state?k={a_token}")
    assert ok.status == 200


def test_garbage_token_rejected(server):
    slug, _ = new_workspace(server, "Garbage Token Co")
    for bad in ("", "x", f"t.{slug}.wrongsecret", "t..y"):
        assert call(server, "GET", f"/t/{slug}/api/state?k={bad}").status == 403


def test_first_visit_sets_scoped_cookie(server):
    slug, token = new_workspace(server, "Cookie Co")
    r = call(server, "GET", f"/t/{slug}?k={token}")
    assert r.status == 200
    cookie = r.headers.get("Set-Cookie")
    assert cookie and cookie.startswith(f"tt_{slug}=")
    assert "HttpOnly" in cookie and f"Path=/t/{slug}" in cookie
    # no ?k= on a later request -> no cookie reissued (state is per-request)
    assert "Set-Cookie" not in call(server, "GET", f"/t/{slug}/api/state?k={token}").headers


# ---------------------------------------------------------------------------
# path handling
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tail", [
    "..",
    "../../../../etc/passwd",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "....//....//etc/passwd",
    "nonexistent.html",
])
def test_run_file_traversal_returns_404(server, tail):
    slug, token = new_workspace(server, f"Traverse {abs(hash(tail)) % 9973} Co")
    r = call(server, "GET", f"/t/{slug}/runs/run_abc123/{tail}?k={token}")
    assert r.status == 404, f"{tail} escaped the run directory"
    assert b"passwd" not in r.body and b"root:" not in r.body


def test_site_asset_traversal_returns_404(server):
    r = call(server, "GET", "/site/../../etc/passwd")
    assert r.status == 404


def test_unknown_route_404(server):
    assert call(server, "GET", "/nope").status == 404
    assert call(server, "POST", "/healthz").status == 404      # method matters


# ---------------------------------------------------------------------------
# body and payload limits
# ---------------------------------------------------------------------------
def test_oversized_body_returns_413(server):
    big = b"x" * (config.MAX_BODY_BYTES + 1)
    r = call(server, "POST", "/api/signup", big, {"Content-Type": "application/json"})
    assert r.status == 413
    assert "too large" in r.json()["error"]


def test_malformed_multipart_returns_422(server):
    slug, token = new_workspace(server, "Multipart Co")
    r = call(server, "POST", f"/t/{slug}/api/upload?k={token}", b"not a multipart body",
             {"Content-Type": "multipart/form-data; boundary=zzz"})
    assert r.status == 422, r.body
    assert r.json()["error"]           # a message, not a stack trace
    assert "Traceback" not in r.body.decode()


def test_missing_boundary_returns_422(server):
    slug, token = new_workspace(server, "No Boundary Co")
    r = call(server, "POST", f"/t/{slug}/api/upload?k={token}", b"whatever",
             {"Content-Type": "multipart/form-data"})
    assert r.status == 422


def test_review_act_bad_json_returns_422(server):
    slug, token = new_workspace(server, "Bad Json Co")
    r = call(server, "POST", f"/t/{slug}/api/review?k={token}", b"{{{",
             {"Content-Type": "application/json"})
    assert r.status == 422


# ---------------------------------------------------------------------------
# upload / seed / delete
# ---------------------------------------------------------------------------
def _upload_body(fields: dict[str, str], filename: str, data: bytes) -> tuple[bytes, str]:
    b = "xBOUNDx"
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
                  .encode())
    out.write(f'--{b}\r\nContent-Disposition: form-data; name="file"; '
              f'filename="{filename}"\r\n\r\n'.encode())
    out.write(data)
    out.write(f"\r\n--{b}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={b}"


META = {"title": "Access Control Policy", "type": "policy", "version": "2.1",
        "owner": "security@example.com", "effective_date": "2026-01-01",
        "expiry_date": "2027-01-01", "topics": "access, mfa", "attested": "on"}
DOC = b"All workforce access to production systems requires multi-factor authentication."


def test_upload_then_delete_removes_the_raw_blob(server):
    """H3: deleting a document used to leave its raw bytes on disk forever."""
    slug, token = new_workspace(server, "Blob Co")
    body, ctype = _upload_body(META, "policy.md", DOC)
    r = call(server, "POST", f"/t/{slug}/api/upload?k={token}", body,
             {"Content-Type": ctype})
    assert r.status == 200, r.body
    sid = r.json()["source_id"]

    updir = config.uploads_dir(slug)
    blobs = list(updir.glob("*")) if updir.is_dir() else []
    assert len(blobs) == 1, "raw blob should have been written"

    d = call(server, "DELETE", f"/t/{slug}/api/upload/{sid}?k={token}")
    assert d.status == 200
    assert list(updir.glob("*")) == [], "raw blob survived the delete"
    assert not (config.evidence_root(slug) / slug / f"{sid}.md").exists()
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM uploads WHERE tenant=?",
                            (slug,)).fetchone()[0] == 0


def test_duplicate_upload_rejected(server):
    slug, token = new_workspace(server, "Dup Co")
    body, ctype = _upload_body(META, "policy.md", DOC)
    assert call(server, "POST", f"/t/{slug}/api/upload?k={token}", body,
                {"Content-Type": ctype}).status == 200
    again = call(server, "POST", f"/t/{slug}/api/upload?k={token}", body,
                 {"Content-Type": ctype})
    assert again.status == 422
    assert "already uploaded" in again.json()["error"]


def test_upload_doc_limit_enforced(server, monkeypatch):
    monkeypatch.setattr(config, "MAX_DOCS_PER_TENANT", 1)
    slug, token = new_workspace(server, "Doc Limit Co")
    body, ctype = _upload_body(META, "policy.md", DOC)
    assert call(server, "POST", f"/t/{slug}/api/upload?k={token}", body,
                {"Content-Type": ctype}).status == 200
    body2, ctype2 = _upload_body({**META, "version": "3.0"}, "policy2.md", DOC + b" Extra.")
    r = call(server, "POST", f"/t/{slug}/api/upload?k={token}", body2,
             {"Content-Type": ctype2})
    assert r.status == 422
    assert "document limit" in r.json()["error"]


def test_seed_is_idempotent(server):
    slug, token = new_workspace(server, "Seed Co")
    first = call(server, "POST", f"/t/{slug}/api/seed?k={token}")
    assert first.status == 200
    n = first.json()["count"]
    assert n > 0, "sample pack seeded nothing"
    second = call(server, "POST", f"/t/{slug}/api/seed?k={token}")
    assert second.status == 200
    assert second.json()["count"] == 0, "seeding twice duplicated the sample pack"
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM uploads WHERE tenant=?",
                            (slug,)).fetchone()[0] == n


def test_state_shape(server):
    slug, token = new_workspace(server, "State Co")
    call(server, "POST", f"/t/{slug}/api/seed?k={token}")
    s = call(server, "GET", f"/t/{slug}/api/state?k={token}").json()
    assert s["org"] == "State Co"
    assert s["run_quota"] == config.RUN_QUOTA
    assert s["runs_remaining"] == config.RUN_QUOTA
    assert s["runs"] == []
    assert len(s["uploads"]) > 0


# ---------------------------------------------------------------------------
# response hardening
# ---------------------------------------------------------------------------
def test_security_headers_on_every_response(server):
    for path, expect in (("/healthz", None), ("/", None), ("/nope", None)):
        r = call(server, "GET", path)
        assert r.headers["X-Content-Type-Options"] == "nosniff", path
        assert r.headers["X-Frame-Options"] == "DENY", path
        assert r.headers["Referrer-Policy"] == "no-referrer", path
        csp = r.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp
        assert "default-src 'self'" in csp
        assert "'unsafe-inline'" in csp        # our pages inline style+script
        # HSTS is pointless (and hostile) on a plaintext localhost port
        assert r.headers.get("Strict-Transport-Security") is None, path
        assert expect is None


def test_csp_allows_every_data_uri_the_landing_page_inlines(server):
    """Each kind of data: URI we inline needs its own CSP directive.

    img-src and font-src were given `data:` when they were added; media-src was
    not, so it fell back to default-src 'self' and the browser silently refused
    the demo film. That was 88 percent of the page's bytes rendering nothing,
    on the hosted build only, with no server-side symptom. Rather than assert
    the three directives we happen to use today, read the built page and
    require a directive for every scheme actually present, so inlining a new
    kind of asset fails here instead of in production.
    """
    page = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    directive = {"image": "img-src", "font": "font-src",
                 "video": "media-src", "audio": "media-src"}
    found = {m for m in re.findall(r"data:(image|font|video|audio)/", page)}
    assert found, "expected the landing page to inline data: URIs"

    csp = call(server, "GET", "/").headers["Content-Security-Policy"]
    parsed = {p.strip().split(" ")[0]: p.strip()
              for p in csp.split(";") if p.strip()}
    for kind in sorted(found):
        name = directive[kind]
        assert name in parsed, f"data:{kind}/ is inlined but {name} is unset, so it falls back to default-src"
        assert "data:" in parsed[name], f"{name} does not permit data:, which blocks every data:{kind}/ URI"


def test_robots_disallows_workspaces(server):
    r = call(server, "GET", "/robots.txt")
    assert r.status == 200
    assert "Disallow: /t/" in r.body.decode()


def test_workspace_responses_are_noindex(server):
    slug, token = new_workspace(server, "Noindex Co")
    r = call(server, "GET", f"/t/{slug}/api/state?k={token}")
    assert r.headers["X-Robots-Tag"] == "noindex"


def test_token_never_reaches_the_log(server):
    """C4: log_request logs self.requestline, which carries ?k=<token>."""
    slug, token = new_workspace(server, "Log Co")
    buf = io.StringIO()
    real, sys.stderr = sys.stderr, buf
    try:
        assert call(server, "GET", f"/t/{slug}/api/state?k={token}").status == 200
    finally:
        sys.stderr = real
    logged = buf.getvalue()
    assert logged.strip(), "the request was not logged at all"
    assert token not in logged, f"workspace token leaked into the log: {logged!r}"
    assert "k=REDACTED" in logged or "?" not in logged
    assert f"/t/{slug}/api/state" in logged


def test_redact_helper():
    assert app._redact("GET /t/a?k=t.a.secret HTTP/1.1") == "GET /t/a?k=REDACTED HTTP/1.1"
    assert app._redact("/t/a?x=1&k=sec&y=2") == "/t/a?x=1&k=REDACTED&y=2"
