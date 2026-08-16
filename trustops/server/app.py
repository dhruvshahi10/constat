"""TrustOps hosted server. stdlib only: ThreadingHTTPServer + route table.

Wave 0 ships /healthz and the dispatch spine; Wave 1 fills in tenant routes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from . import config, db  # noqa: E402

ROBOTS = "User-agent: *\nDisallow: /t/\n"

# (method, compiled pattern) -> handler name; filled out in Wave 1
ROUTES: list[tuple[str, re.Pattern, str]] = [
    ("GET", re.compile(r"^/healthz$"), "healthz"),
    ("GET", re.compile(r"^/robots\.txt$"), "robots"),
    ("GET", re.compile(r"^/$"), "landing"),
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

    def _dispatch(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        for m, pat, name in ROUTES:
            if m != method:
                continue
            match = pat.match(path)
            if match:
                try:
                    getattr(self, name)(*match.groups())
                except Exception as exc:  # noqa: BLE001 — boundary: never leak a traceback
                    self._json({"error": f"{type(exc).__name__}"}, 500)
                return
        self._json({"error": "not found"}, 404)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[trustops] %s %s\n" % (self.address_string(), fmt % args))

    # -- routes --------------------------------------------------------------
    def healthz(self) -> None:
        self._json({"ok": True})

    def robots(self) -> None:
        self._send(200, ROBOTS.encode(), "text/plain")

    def landing(self) -> None:
        site = ROOT / "site" / "index.html"
        if site.is_file():
            self._html(site.read_text(encoding="utf-8"))
        else:
            self._html("<title>TrustOps</title><p>TrustOps hosted: landing ships in Wave 2.</p>")


def main() -> None:
    ap = argparse.ArgumentParser(description="TrustOps hosted server")
    ap.add_argument("--host", default=config.HOST)
    ap.add_argument("--port", type=int, default=config.PORT)
    args = ap.parse_args()

    db.init()
    if config.EPHEMERAL_SECRET:
        sys.stderr.write("[trustops] WARNING: TRUSTOPS_SECRET unset; tokens die on restart\n")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    sys.stderr.write(f"[trustops] serving on http://{args.host}:{args.port}\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
