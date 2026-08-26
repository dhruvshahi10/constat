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

import os
import re
import shutil
import tempfile
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
    # Clear the contents but keep the directory and any .vercel link inside it:
    # rmtree here silently unlinks the deploy target, and the next deploy then
    # creates a brand new project named after the folder.
    OUT.mkdir(parents=True, exist_ok=True)
    for child in OUT.iterdir():
        if child.name == ".vercel":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()

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

    # site/publish/ is in .gitignore so the generated output never lands in a
    # commit — but the Vercel CLI falls back to .gitignore when it is run
    # inside a git repository, and would therefore upload nothing at all. An
    # explicit .vercelignore takes precedence and keeps the two concerns apart.
    (OUT / ".vercelignore").write_text(
        "# Deliberately empty. Present so the Vercel CLI does not fall back to\n"
        "# the repository .gitignore, which excludes this whole directory.\n",
        encoding="utf-8")

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

    # Deploying straight from site/publish/ does not work. The directory is
    # gitignored so the generated 4MB output never lands in a commit, but the
    # Vercel CLI resolves the surrounding git repository and then uploads
    # nothing, producing a deployment with no files that answers 404 on every
    # route — while still reporting success. A .vercelignore does not override
    # it. Staging a copy outside the repository sidesteps git entirely.
    if os.environ.get("VERCEL"):
        # On the build host the output directory IS the deploy; staging a copy
        # outside the repo is only needed for a local push from a git worktree.
        print(f"\nsite/publish/ ready — {sum(1 for _ in OUT.rglob('*.html'))} pages, no backend")
        return 0
    stage = Path(tempfile.gettempdir()) / "constat-deploy"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(OUT, stage, ignore=shutil.ignore_patterns(".vercel"))

    print(f"\nsite/publish/ ready — {sum(1 for _ in OUT.rglob('*.html'))} pages, no backend")
    print(f"staged for deploy at {stage}")
    print("deploy with:")
    print(f"  cd {stage} && vercel link --yes --project constat && \\")
    print("    URL=$(vercel --prod --yes | grep -oE 'https://[a-z0-9-]+\\.vercel\\.app' | head -1) && \\")
    print("    vercel alias set \"$URL\" constat.dhruvshahi.com")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
