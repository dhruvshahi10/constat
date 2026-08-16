"""TrustOps hosted server. stdlib only: ThreadingHTTPServer + route table.

Auth model: signup mints a bearer token bound to the tenant slug (hashed at
rest). First visit with ?k=<token> sets an HttpOnly cookie; thereafter the
cookie authenticates. The slug inside the token must equal the path slug, so
one tenant's cookie is inert against another's workspace.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from http import cookies as http_cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ..envfile import load_env  # noqa: E402
from . import auth, config, db, extract, limits, pages, review, runqueue  # noqa: E402

ROBOTS = "User-agent: *\nDisallow: /t/\n"
NOINDEX = {"X-Robots-Tag": "noindex"}
CTYPES = {".html": "text/html; charset=utf-8", ".json": "application/json",
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
    server_version = "trustops"

    # -- plumbing ------------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200,
              extra: dict[str, str] | None = None) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json", extra)

    def _html(self, text: str, code: int = 200,
              extra: dict[str, str] | None = None) -> None:
        self._send(code, text.encode(), "text/html; charset=utf-8", extra)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > config.MAX_BODY_BYTES:
            raise ValueError("body too large")
        return self.rfile.read(n) if n else b""

    def _client_ip(self) -> str:
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

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
            except (extract.ExtractError, runqueue.QueueError,
                    review.ReviewError) as exc:
                self._json({"error": str(exc)}, 422)
            except Exception:  # noqa: BLE001 — boundary: log, never leak
                sys.stderr.write(f"[trustops] 500 on {method} {path}:\n"
                                 f"{__import__('traceback').format_exc()}\n")
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

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[trustops] %s %s\n" % (self.address_string(), fmt % args))

    # -- public routes -------------------------------------------------------
    def healthz(self) -> None:
        self._json({"ok": True})

    def robots(self) -> None:
        self._send(200, ROBOTS.encode(), "text/plain")

    def landing(self) -> None:
        site = ROOT / "site" / "index.html"
        if site.is_file():
            self._html(site.read_text(encoding="utf-8"))
        else:
            self._html("<title>TrustOps</title><p>TrustOps hosted. Landing ships in Wave 2. "
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
        if not limits.signup_allowed(ip):
            self._json({"error": "Signup limit reached from this network today."}, 429)
            return
        try:
            data = json.loads(self._body() or b"{}")
        except json.JSONDecodeError:
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
        with db.connect() as conn:
            taken = {r["slug"] for r in conn.execute("SELECT slug FROM tenants")}
            slug = auth.make_slug(org, taken)
            token, token_hash = auth.mint_token(slug)
            conn.execute(
                "INSERT INTO tenants(slug, org, email, token_hash, created_at, "
                "expires_at, run_quota) VALUES(?,?,?,?,?,?,?)",
                (slug, org, email, token_hash, db.now(),
                 db.in_days(config.TENANT_TTL_DAYS), config.RUN_QUOTA))
        limits.record_signup(ip)
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
        from . import multipart
        if limits.doc_count(slug) >= config.MAX_DOCS_PER_TENANT:
            raise extract.ExtractError("Workspace document limit (20) reached.")
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
        with db.connect() as conn:
            dup = conn.execute("SELECT source_id FROM uploads WHERE tenant=? AND sha256=?",
                               (slug, sha)).fetchone()
            if dup:
                raise extract.ExtractError(
                    f"Identical document already uploaded as {dup['source_id']}.")
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
        src_dir = ROOT / "data" / "evidence" / "acme"
        count = 0
        with db.connect() as conn:
            for f in sorted(src_dir.glob("*.md")):
                text = f.read_text(encoding="utf-8")
                import hashlib
                sha = hashlib.sha256(text.encode()).hexdigest()
                sid = f.stem
                dup = conn.execute(
                    "SELECT 1 FROM uploads WHERE tenant=? AND sha256=?",
                    (slug, sha)).fetchone()
                if dup or limits.doc_count(slug) + count >= config.MAX_DOCS_PER_TENANT:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO uploads(tenant, source_id, filename, sha256, "
                    "bytes, approved, created_at) VALUES(?,?,?,?,?,1,?)",
                    (slug, sid, f"{sid}.md (sample)", sha, len(text), db.now()))
                extract.persist(slug, sid, text)
                count += 1
        self._json({"count": count})

    def delete_upload(self, slug: str, source_id: str) -> None:
        with db.connect() as conn:
            conn.execute("DELETE FROM uploads WHERE tenant=? AND source_id=?",
                         (slug, source_id))
        target = config.evidence_root(slug) / slug / f"{source_id}.md"
        if target.is_file():
            target.unlink()
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
        runs = [{"id": r["id"], "items": review.queue_items(Path(r["dir"]))}
                for r in done]
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
    ap = argparse.ArgumentParser(description="TrustOps hosted server")
    ap.add_argument("--host", default=config.HOST)
    ap.add_argument("--port", type=int, default=config.PORT)
    args = ap.parse_args()

    db.init()
    runqueue.recover_and_start()
    limits.start_sweeper()
    if config.EPHEMERAL_SECRET:
        sys.stderr.write("[trustops] WARNING: TRUSTOPS_SECRET unset; tokens die on restart\n")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    sys.stderr.write(f"[trustops] serving on http://{args.host}:{args.port}\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
