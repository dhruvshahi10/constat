"""Assemble the backend-free site for static hosting.

The hosted application — workspaces, upload, runs, review — needs a container
and a persistent disk. The marketing site, the trust centre, how-it-works and
pricing do not: they are complete HTML. This puts those four into site/publish/
so they can go on a static host today while the application is hosted
separately later.

    .venv/bin/python scripts/build_site_demo.py    # the static landing page
    .venv/bin/python scripts/build_pages.py        # trust / pricing / how-it-works
    .venv/bin/python scripts/build_publish.py      # assemble site/publish/
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = SITE / "publish"
PAGES = ("trust", "pricing", "how-it-works")

# Backend references are matched in link and fetch position only. A bare
# substring search is useless here: the landing page inlines several megabytes
# of base64 font and video, and a three-character sequence like "/t/" occurs in
# that by chance — eighteen times, not one of them a URL.
BACKEND_PATTERNS = [
    re.compile(r'(?:href|src|action)\s*=\s*["\'](?:/api/|/t/)'),
    re.compile(r'fetch\s*\(\s*["\'`](?:/api/|/t/)'),
    re.compile(r'["\'`]https?://localhost'),
]


def main() -> int:
    landing = SITE / "static" / "index.html"
    if not landing.is_file():
        print("run scripts/build_site_demo.py first", file=sys.stderr)
        return 2
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shutil.copy2(landing, OUT / "index.html")
    print(f"  index.html                {landing.stat().st_size // 1024:>5}KB")
    for name in PAGES:
        src = SITE / name / "index.html"
        if not src.is_file():
            print(f"  {name}: missing — run scripts/build_pages.py", file=sys.stderr)
            return 2
        (OUT / name).mkdir()
        shutil.copy2(src, OUT / name / "index.html")
        print(f"  {name}/index.html".ljust(28) + f"{src.stat().st_size // 1024:>5}KB")

    bad = []
    for page in sorted(OUT.rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        for pat in BACKEND_PATTERNS:
            for m in pat.finditer(text):
                bad.append(f"{page.relative_to(OUT)}: {m.group(0)[:48]}")
    if bad:
        print("\nrefusing to publish — these expect a backend:", file=sys.stderr)
        for line in bad:
            print(f"  {line}", file=sys.stderr)
        return 2

    print(f"\nsite/publish/ ready — {sum(1 for _ in OUT.rglob('*.html'))} pages, no backend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
