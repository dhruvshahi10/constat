"""Pramana AI hosted server. stdlib only: ThreadingHTTPServer + route table.

Auth model: signup mints a bearer token bound to the tenant slug (hashed at
rest). First visit with ?k=<token> sets an HttpOnly cookie; thereafter the
cookie authenticates. The slug inside the token must equal the path slug, so
one tenant's cookie is inert against another's workspace.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from http import cookies as http_cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ..envfile import load_env  # noqa: E402
from . import auth, config, db, extract, limits, multipart, pages, review, runqueue  # noqa: E402

ROBOTS = "User-agent: *\nDisallow: /t/\n"
NOINDEX = {"X-Robots-Tag": "noindex"}

# Our pages inline both <style> and <script>, so 'unsafe-inline' is required;
# what this policy actually buys is that nothing may be pulled from, or posted
# to, an origin that is not us — the exfiltration path for a leaked token.
# media-src needs data: for the same reason img-src and font-src do: the
# landing page is one self-contained file and inlines the demo film as a data
# URI. It was omitted, so media-src fell back to default-src 'self' and the
# browser refused the video, silently, on the hosted build only. That is 5.3MB
# of the page, 88 percent of its bytes, rendering nothing.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self' data:; media-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": CSP,
}

# Workspace tokens travel as ?k=<token> on the first visit. They must never be
# written to a log line, an error body, or anything else durable.
_TOKEN_QS = re.compile(r"([?&]k=)[^&\s]+")


def _redact(text: str) -> str:
    return _TOKEN_QS.sub(r"\1REDACTED", text)


class BodyTooLarge(ValueError):
    """Declared Content-Length over the ceiling -> 413, body never read."""


# Slowloris ceiling: ThreadingHTTPServer spawns a thread per connection and
# never bounds them, so an idle-connection flood is free memory exhaustion.
_conn_slots = threading.BoundedSemaphore(config.MAX_CONNECTIONS)
_BUSY_BODY = b'{"error": "Server busy. Try again shortly."}'
_BUSY = (b"HTTP/1.1 503 Service Unavailable\r\n"
         b"Content-Type: application/json\r\n"
         b"Content-Length: " + str(len(_BUSY_BODY)).encode() + b"\r\n"
         b"Connection: close\r\n\r\n" + _BUSY_BODY)
CTYPES = {".html": "text/html; charset=utf-8", ".json": "application/json",
          ".mp4": "video/mp4", ".jpg": "image/jpeg", ".webm": "video/webm",
          ".jsonl": "text/plain; charset=utf-8",
          ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

SLUG = r"([a-z0-9][a-z0-9-]{1,40})"
ROUTES: list[tuple[str, re.Pattern, str, bool]] = [  # (method, pattern, handler, needs_auth)
    ("GET",    re.compile(r"^/healthz$"), "healthz", False),
    ("GET",    re.compile(r"^/robots\.txt$"), "robots", False),
    ("GET",    re.compile(r"^/$"), "landing", False),
    ("GET",    re.compile(r"^/site/([A-Za-z0-9._/-]+)$"), "site_asset", False),
    ("POST",   re.compile(r"^/api/signup$"), "signup", False),
    ("GET",    re.compile(rf"^/t/{SLUG}$"), "workspace", True),
    ("GET",    re.compile(rf"^/t/{SLUG}/api/state$"), "state", True),
    ("POST",   re.compile(rf"^/t/{SLUG}/api/upload$"), "upload", True),
    ("POST",   re.compile(rf"^/t/{SLUG}/api/seed$"), "seed", True),
    ("DELETE", re.compile(rf"^/t/{SLUG}/api/upload/([A-Z0-9-]+)$"), "delete_upload", True),
    ("POST",   re.compile(rf"^/t/{SLUG}/api/run$"), "start_run", True),
    ("GET",    re.compile(rf"^/t/{SLUG}/api/run/(run_[a-f0-9]+)$"), "run_status", True),
    ("GET",    re.compile(rf"^/t/{SLUG}/runs/(run_[a-f0-9]+)/([A-Za-z0-9._-]+)$"), "run_file", True),
    ("GET",    re.compile(rf"^/t/{SLUG}/review$"), "review_queue", True),
    ("POST",   re.compile(rf"^/t/{SLUG}/api/review$"), "review_act", True),
]


class Handler(BaseHTTPRequestHandler):
    server_version = "pramana"
    # Deliberately left at HTTP/1.0 (close-per-request): it means an aborted
    # read (e.g. a 413 refused before the body is drained) can never desync a
    # keep-alive connection.
    # StreamRequestHandler.setup() applies this to the connection socket, so a
    # client that opens a socket and dribbles bytes is cut off instead of
    # holding a thread forever.
    timeout = config.SOCKET_TIMEOUT_S

    # -- connection admission -------------------------------------------------
    def end_headers(self) -> None:
        """Every response gets the security headers, including the ones stdlib
        writes for us. `send_error` (malformed request line, unsupported method)
        and the over-capacity 503 both bypass `_send`, so hooking the single
        point every response passes through is what makes the guarantee true
        rather than nearly true. Guarded so `_send`'s explicit headers are not
        duplicated."""
        if not getattr(self, "_sec_sent", False):
            self._sec_sent = True
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
        super().end_headers()

    def setup(self) -> None:
        super().setup()
        self._slot = _conn_slots.acquire(blocking=False)

    def handle(self) -> None:
        if not getattr(self, "_slot", False):
            self.close_connection = True
            try:
                self.wfile.write(_BUSY)
            except OSError:
                pass
            return
        super().handle()

    def finish(self) -> None:
        try:
            super().finish()
        finally:
            if getattr(self, "_slot", False):
                self._slot = False
                _conn_slots.release()

    # -- plumbing ------------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # SECURITY_HEADERS are added by end_headers() for every response
        if not self._is_local():
            # only meaningful over TLS, and pinning HSTS on localhost breaks
            # every developer's browser for that port
            self.send_header("Strict-Transport-Security",
                             "max-age=31536000; includeSubDomains")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _is_local(self) -> bool:
        host = (self.headers.get("Host", "") or "").split(":")[0].lower()
        return host in ("localhost", "127.0.0.1", "::1", "")

    def _json(self, obj: dict, code: int = 200,
              extra: dict[str, str] | None = None) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json", extra)

    def _html(self, text: str, code: int = 200,
              extra: dict[str, str] | None = None) -> None:
        self._send(code, text.encode(), "text/html; charset=utf-8", extra)

    def _body(self) -> bytes:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise BodyTooLarge("body too large") from None
        if n < 0 or n > config.MAX_BODY_BYTES:
            raise BodyTooLarge("body too large")
        return self.rfile.read(n) if n else b""

    def _client_ip(self) -> str:
        """The last X-Forwarded-For hop, i.e. the one our proxy appended.

        Proxies *append* to X-Forwarded-For, so the first value is whatever the
        client typed — free rate-limit bypass. Exactly one trusted proxy
        (Render) sits in front of us, so the last entry is the real peer.
        """
        fwd = self.headers.get("X-Forwarded-For", "")
        if fwd:
            hop = fwd.split(",")[-1].strip()
            if hop:
                return hop
        return self.client_address[0]

    def _tenant_row(self, slug: str):
        with db.connect() as conn:
            return conn.execute(
                "SELECT * FROM tenants WHERE slug=? AND status='active'", (slug,)).fetchone()

    def _authed(self, slug: str) -> tuple[bool, bool]:
        """Returns (ok, via_query) — via_query means set the cookie on response."""
        row = self._tenant_row(slug)
        if row is None:
            return False, False
        qs = parse_qs(urlparse(self.path).query)
        token = (qs.get("k") or [None])[0]
        via_query = token is not None
        if token is None:
            jar = http_cookies.SimpleCookie(self.headers.get("Cookie", ""))
            morsel = jar.get(f"tt_{slug}")
            token = morsel.value if morsel else None
        if not token or auth.token_slug(token) != slug:
            return False, False
        return auth.token_matches(token, row["token_hash"]), via_query

    def _dispatch(self, method: str) -> None:
        path = urlparse(self.path).path
        # instance state, so it must be reset per request, not only assigned
        # on the branch that happens to authenticate
        self._cookie_pending = False
        for m, pat, name, needs_auth in ROUTES:
            if m != method:
                continue
            match = pat.match(path)
            if not match:
                continue
            try:
                if needs_auth:
                    ok, via_query = self._authed(match.group(1))
                    if not ok:
                        self._json({"error": "This workspace link is invalid or expired."},
                                   403, NOINDEX)
                        return
                    self._cookie_pending = via_query
                getattr(self, name)(*match.groups())
            except BodyTooLarge:
                self.close_connection = True   # body not drained; never reuse
                self._json({"error": "That request was too large."}, 413)
            except (extract.ExtractError, runqueue.QueueError, review.ReviewError,
                    limits.LimitError, multipart.MultipartError) as exc:
                self._json({"error": str(exc)}, 422)
            except json.JSONDecodeError:
                self._json({"error": "Request body was not valid JSON."}, 422)
            except Exception:  # noqa: BLE001 — boundary: log, never leak
                sys.stderr.write(f"[pramana] 500 on {method} {path}:\n"
                                 f"{_redact(__import__('traceback').format_exc())}\n")
                self._json({"error": "Internal error. It has been logged."}, 500)
            return
        self._json({"error": "not found"}, 404)

    def _auth_cookie(self, slug: str) -> dict[str, str]:
        if not getattr(self, "_cookie_pending", False):
            return dict(NOINDEX)
        qs = parse_qs(urlparse(self.path).query)
        token = qs["k"][0]
        return {**NOINDEX,
                "Set-Cookie": f"tt_{slug}={token}; Path=/t/{slug}; HttpOnly; "
                              f"SameSite=Lax; Max-Age=1209600; Secure"}

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def log_request(self, code="-", size="-") -> None:  # noqa: A002
        """Log method + path + status, never the query string.

        The base implementation logs self.requestline, which on a first visit
        is `GET /t/acme?k=t.acme.<secret> HTTP/1.1`. That token is the only
        credential a workspace has and it is valid for fourteen days; putting
        it in a log file hands the workspace to anyone who can read logs.
        """
        try:
            path = urlparse(self.path).path
        except Exception:  # noqa: BLE001 — a malformed path must still log
            path = "-"
        self.log_message('"%s %s" %s %s', self.command, path,
                         getattr(code, "value", code), size)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[pramana] %s %s\n"
                         % (self.address_string(), _redact(fmt % args)))

    # -- public routes -------------------------------------------------------
    def healthz(self) -> None:
        """Green only if the thing that does the work is actually alive.

        The run worker is a single thread; when it died, every run for every
        tenant queued forever while this endpoint kept saying "ok". A health
        check that cannot go red is decoration.
        """
        alive = runqueue.worker_alive()
        self._json({"ok": alive, "worker": "alive" if alive else "dead"},
                   200 if alive else 503)

    def robots(self) -> None:
        self._send(200, ROBOTS.encode(), "text/plain")

    def landing(self) -> None:
        site = ROOT / "site" / "index.html"
        if site.is_file():
            self._html(site.read_text(encoding="utf-8"))
        else:
            self._html("<title>Pramana AI</title><p>Pramana AI hosted. Landing ships in Wave 2. "
                       "<a href='/healthz'>healthz</a></p>")

    def site_asset(self, rel: str) -> None:
        target = (ROOT / "site" / rel).resolve()
        if not (target.is_file() and target.is_relative_to((ROOT / "site").resolve())):
            self._json({"error": "not found"}, 404)
            return
        ctype = CTYPES.get(target.suffix,
                           "image/png" if target.suffix == ".png" else
                           "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)

    def signup(self) -> None:
        ip = self._client_ip()
        try:
            data = json.loads(self._body() or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "invalid JSON"}, 422)
            return
        if not isinstance(data, dict):
            self._json({"error": "invalid JSON"}, 422)
            return
        if data.get("website"):  # honeypot field: humans never fill it
            self._json({"error": "Signup limit reached from this network today."}, 429)
            return
        org = str(data.get("org", "")).strip()
        email = str(data.get("email", "")).strip()
        if not 2 <= len(org) <= 80:
            self._json({"error": "Organization name must be 2 to 80 characters."}, 422)
            return
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            self._json({"error": "A valid work email is required."}, 422)
            return
        if not data.get("consent"):
            # the checkbox is in the form, but the form is not the boundary
            self._json({"error": "You must accept the Terms and Privacy Notice."}, 422)
            return

        # One transaction: count the day's signups, record this one, and create
        # the tenant. Split apart, N concurrent requests all read the same
        # under-cap count and all succeed.
        try:
            with db.immediate() as conn:
                limits.claim_signup(conn, ip)
                taken = {r["slug"] for r in conn.execute("SELECT slug FROM tenants")}
                slug = auth.make_slug(org, taken)
                token, token_hash = auth.mint_token(slug)
                conn.execute(
                    "INSERT INTO tenants(slug, org, email, token_hash, created_at, "
                    "expires_at, run_quota, consent_at) VALUES(?,?,?,?,?,?,?,?)",
                    (slug, org, email, token_hash, db.now(),
                     db.in_days(config.TENANT_TTL_DAYS), config.RUN_QUOTA, db.now()))
        except limits.LimitError as exc:
            self._json({"error": str(exc)}, 429)
            return
        config.tenant_dir(slug).mkdir(parents=True, exist_ok=True)
        self._json({"workspace": f"/t/{slug}?k={token}", "slug": slug,
                    "note": "Save this link. It is the only key to your workspace."})

    # -- tenant routes -------------------------------------------------------
    def workspace(self, slug: str) -> None:
        row = self._tenant_row(slug)
        self._html(pages.workspace(slug, row["org"]), extra=self._auth_cookie(slug))

    def state(self, slug: str) -> None:
        row = self._tenant_row(slug)
        with db.connect() as conn:
            ups = [dict(r) for r in conn.execute(
                "SELECT source_id, filename, approved, created_at FROM uploads "
                "WHERE tenant=? ORDER BY created_at", (slug,))]
            runs = [runqueue.status(slug, r["id"]) for r in conn.execute(
                "SELECT id FROM runs WHERE tenant=? ORDER BY queued_at DESC", (slug,))]
        self._json({"org": row["org"], "uploads": ups, "runs": runs,
                    "run_quota": row["run_quota"],
                    "runs_remaining": limits.runs_remaining(slug)}, extra=NOINDEX)

    def upload(self, slug: str) -> None:
        # cheap pre-check so a hopeless upload fails before we parse megabytes;
        # the binding check is the atomic one below
        if limits.doc_count(slug) >= config.MAX_DOCS_PER_TENANT:
            raise limits.LimitError(
                f"Workspace document limit ({config.MAX_DOCS_PER_TENANT}) reached.")
        body = self._body()
        parts = multipart.parse(body, self.headers.get("Content-Type", ""))
        if "file" not in parts or parts["file"][0] is None:
            raise extract.ExtractError("No file in the upload.")
        filename, data = parts["file"]
        form = {k: multipart.text_field(parts, k) for k in
                ("title", "type", "version", "owner", "effective_date",
                 "expiry_date", "topics", "attested")}
        meta = extract.validate_meta(form)
        text = extract.extract_text(filename, data)
        source_id, sha, file_text = extract.synthesize(meta, text, slug)
        # claim the slot, the byte budget and the row together, or not at all
        with db.immediate() as conn:
            dup = conn.execute("SELECT source_id FROM uploads WHERE tenant=? AND sha256=?",
                               (slug, sha)).fetchone()
            if dup:
                raise extract.ExtractError(
                    f"Identical document already uploaded as {dup['source_id']}.")
            limits.claim_upload_slot(conn, slug, len(data))
            conn.execute(
                "INSERT INTO uploads(tenant, source_id, filename, sha256, bytes, "
                "approved, created_at) VALUES(?,?,?,?,?,?,?)",
                (slug, source_id, filename, sha, len(data),
                 1 if meta["approval_status"] == "approved" else 0, db.now()))
        extract.persist(slug, source_id, file_text)
        updir = config.uploads_dir(slug)
        updir.mkdir(parents=True, exist_ok=True)
        (updir / f"{sha}{Path(filename).suffix.lower()}").write_bytes(data)
        self._json({"source_id": source_id, "approved": meta["approval_status"] == "approved"})

    def seed(self, slug: str) -> None:
        """Copy the synthetic sample pack so a demo never dead-ends."""
        import hashlib
        src_dir = ROOT / "data" / "evidence" / "acme"
        count = 0
        persisted: list[tuple[str, str]] = []
        # one transaction so a double-click cannot seed the pack twice, and so
        # the doc-count ceiling is read from inside the same write lock
        with db.immediate() as conn:
            for f in sorted(src_dir.glob("*.md")):
                text = f.read_text(encoding="utf-8")
                sha = hashlib.sha256(text.encode()).hexdigest()
                sid = f.stem
                dup = conn.execute(
                    "SELECT 1 FROM uploads WHERE tenant=? AND sha256=?",
                    (slug, sha)).fetchone()
                have = conn.execute("SELECT COUNT(*) FROM uploads WHERE tenant=?",
                                    (slug,)).fetchone()[0]
                if dup or have >= config.MAX_DOCS_PER_TENANT:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO uploads(tenant, source_id, filename, sha256, "
                    "bytes, approved, created_at) VALUES(?,?,?,?,?,1,?)",
                    (slug, sid, f"{sid}.md (sample)", sha, len(text), db.now()))
                persisted.append((sid, text))
                count += 1
        for sid, text in persisted:
            extract.persist(slug, sid, text)
        self._json({"count": count})

    def delete_upload(self, slug: str, source_id: str) -> None:
        # read the blob's identity before the row that names it is gone, or the
        # raw upload becomes an orphan on disk that nothing can ever reclaim
        with db.immediate() as conn:
            row = conn.execute(
                "SELECT sha256, filename FROM uploads WHERE tenant=? AND source_id=?",
                (slug, source_id)).fetchone()
            conn.execute("DELETE FROM uploads WHERE tenant=? AND source_id=?",
                         (slug, source_id))
        target = config.evidence_root(slug) / slug / f"{source_id}.md"
        if target.is_file():
            target.unlink()
        if row is not None:
            limits.delete_upload_blob(slug, row["sha256"], row["filename"])
        self._json({"deleted": source_id})

    def start_run(self, slug: str) -> None:
        row = self._tenant_row(slug)
        if limits.doc_count(slug) < 1:
            raise runqueue.QueueError("Upload at least one document (or seed the "
                                      "sample pack) before running.")
        load_env(ROOT)
        import os
        drafter = config.HOSTED_DRAFTER if os.environ.get("GEMINI_API_KEY") else "mock"
        run_id = runqueue.enqueue(slug, row["org"], drafter)
        self._json({"run_id": run_id})

    def run_status(self, slug: str, run_id: str) -> None:
        self._json(runqueue.status(slug, run_id), extra=NOINDEX)

    def run_file(self, slug: str, run_id: str, filename: str) -> None:
        base = (config.runs_dir(slug) / run_id).resolve()
        target = (base / filename).resolve()
        if not (target.is_file() and target.is_relative_to(base)):
            self._json({"error": "not found"}, 404)
            return
        self._send(200, target.read_bytes(),
                   CTYPES.get(target.suffix, "application/octet-stream"), NOINDEX)

    def review_queue(self, slug: str) -> None:
        row = self._tenant_row(slug)
        with db.connect() as conn:
            done = conn.execute(
                "SELECT id, dir FROM runs WHERE tenant=? AND status='done' "
                "ORDER BY finished_at DESC", (slug,)).fetchall()
        # a pruned run has no state.json; skipping it keeps the queue usable
        # instead of letting one old run 500 the page for the whole workspace
        runs = []
        for r in done:
            if not r["dir"] or not (Path(r["dir"]) / "state.json").is_file():
                continue
            runs.append({"id": r["id"], "items": review.queue_items(Path(r["dir"]))})
        self._html(pages.review_page(slug, row["org"], runs), extra=self._auth_cookie(slug))

    def review_act(self, slug: str) -> None:
        data = json.loads(self._body() or b"{}")
        run_id = str(data.get("run_id", ""))
        with db.connect() as conn:
            row = conn.execute(
                "SELECT dir FROM runs WHERE id=? AND tenant=? AND status='done'",
                (run_id, slug)).fetchone()
        if row is None:
            raise review.ReviewError("Run not found in this workspace.")
        out = review.act(Path(row["dir"]), str(data.get("question_id", "")),
                         str(data.get("action", "")), str(data.get("reviewer", "")),
                         str(data.get("note", "")))
        self._json(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Pramana AI hosted server")
    ap.add_argument("--host", default=config.HOST)
    ap.add_argument("--port", type=int, default=config.PORT)
    args = ap.parse_args()

    db.init()
    runqueue.recover_and_start()
    limits.start_sweeper()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    sys.stderr.write(f"[pramana] serving on http://{args.host}:{args.port}\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
