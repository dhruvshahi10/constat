"""Record a real screen capture of the hosted product journey, then compress it.

Boots the actual stdlib server (trustops.server.app) against a throwaway data
dir, drives it with Playwright exactly like a calm human would — signup, empty
workspace, seed the sample pack, run the questionnaire with the offline mock
drafter, read the report — and records the whole thing as video. The raw
Playwright webm is then transcoded (scaled to 960px wide, 24fps) with the
ffmpeg on PATH if there is one, else Playwright's bundled ffmpeg (VP8-only
build), stepping the bitrate down until the file is under the 2.2MB budget.

Outputs:
    site/img/demo.webm         the compressed film
    site/img/demo_poster.jpg   a 960px JPEG poster from early in the report

Regenerate with:
    .venv/bin/python scripts/capture_demo_video.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / ".venv" / "bin" / "python"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
PW_FFMPEG = "/opt/pw-browsers/ffmpeg-1011/ffmpeg-linux"

PORT = int(os.environ.get("DEMO_PORT", "8872"))
BASE = f"http://127.0.0.1:{PORT}"
DATA_DIR = Path(os.environ.get(
    "DEMO_DATA",
    "/tmp/claude-0/-home-user-trustops/187c9557-541a-5d75-aeb5-7fc0bc5330db/"
    "scratchpad/viddata"))
WORK = DATA_DIR.parent / "vidwork"

OUT_VIDEO = ROOT / "site" / "img" / "demo.webm"
OUT_POSTER = ROOT / "site" / "img" / "demo_poster.jpg"
VIDEO_BUDGET = 2_200_000       # bytes
POSTER_BUDGET = 60_000         # bytes

VIEWPORT = {"width": 1280, "height": 800}


# ---------------------------------------------------------------- server ----
def start_server() -> subprocess.Popen:
    env = {**os.environ, "TRUSTOPS_DATA": str(DATA_DIR), "PORT": str(PORT)}
    # the film must show the deterministic offline drafter, never a live model
    env.pop("GEMINI_API_KEY", None)
    proc = subprocess.Popen(
        [str(VENV_PY), "-m", "trustops.server.app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/healthz", timeout=2) as r:
                if json.loads(r.read()).get("ok"):
                    return proc
        except Exception:
            time.sleep(0.3)
        if proc.poll() is not None:
            break
    err = proc.stderr.read().decode() if proc.stderr else ""
    raise SystemExit(f"server did not come up on {BASE}\n{err}")


def signup() -> str:
    body = json.dumps({"org": "Northwind Systems",
                       "email": "security@northwind.example",
                       "consent": True}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/signup", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    if "workspace" not in data:
        raise SystemExit(f"signup failed: {data}")
    return data["workspace"]      # /t/<slug>?k=<token>


# ------------------------------------------------------------- the film ----
def smooth_scroll(page, y: int, settle_ms: int = 1600) -> None:
    page.evaluate(f"window.scrollTo({{top: {y}, behavior: 'smooth'}})")
    page.wait_for_timeout(settle_ms)


def smooth_to(page, selector: str, settle_ms: int = 1800) -> bool:
    found = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return false;
            el.scrollIntoView({behavior: 'smooth', block: 'center'});
            return true;
        }""", selector)
    page.wait_for_timeout(settle_ms)
    return bool(found)


def film(workspace_path: str, video_dir: Path, poster_raw: Path) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROME, headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--force-device-scale-factor=1", "--hide-scrollbars"])
        ctx = browser.new_context(
            viewport=VIEWPORT, record_video_dir=str(video_dir),
            record_video_size=VIEWPORT, device_scale_factor=1)
        page = ctx.new_page()

        # 1 — the empty workspace, fresh from signup
        page.goto(BASE + workspace_path, wait_until="networkidle")
        page.wait_for_timeout(2200)

        # 2 — seed the sample evidence pack, watch documents land
        smooth_to(page, "#seedbtn", 900)
        page.click("#seedbtn")
        page.wait_for_selector("#docs .doc", timeout=15_000)
        page.wait_for_timeout(1400)
        smooth_to(page, "#docs", 1200)
        page.wait_for_timeout(1600)

        # 3 — start the run; the offline drafter shows per-question progress
        page.wait_for_function(
            "() => !document.getElementById('runbtn').disabled", timeout=15_000)
        smooth_to(page, "#runbtn", 1000)
        page.click("#runbtn")
        # let the ticker play: progress bar, then the completion card
        page.wait_for_selector("#resultcard", timeout=180_000)
        page.wait_for_timeout(600)
        smooth_to(page, "#resultcard", 1200)
        page.wait_for_timeout(2200)

        # 4 — the run report, read like a human: dial, tiles, refusals,
        #     one refusal's provenance
        href = page.get_attribute("#resultcard a.abtn-primary", "href")
        page.goto(BASE + href, wait_until="networkidle")
        page.wait_for_timeout(1800)
        page.screenshot(path=str(poster_raw), type="jpeg", quality=88)

        smooth_to(page, ".viz", 2000)               # coverage dial + stat tiles
        page.wait_for_timeout(1200)
        smooth_to(page, ".stackbar", 2000)          # the refusal bar
        page.wait_for_timeout(1200)
        # one refusal's provenance line ("no citation released · gap named")
        if not smooth_to(page, ".prov.p-warn", 2200):
            smooth_to(page, "table tbody tr:nth-child(4)", 2200)
        page.wait_for_timeout(1600)
        smooth_scroll(page, 0, 1800)                # settle back on the verdict
        page.wait_for_timeout(800)

        page.close()
        video_path = Path(page.video.path())
        ctx.close()
        browser.close()
    return video_path


# ------------------------------------------------------------ compression ----
def pick_ffmpeg() -> tuple[str, str]:
    """Returns (binary, codec). Prefers a full ffmpeg (VP9); falls back to
    Playwright's bundled build, which only carries the VP8 encoder."""
    full = shutil.which("ffmpeg")
    if full:
        return full, "vp9"
    if Path(PW_FFMPEG).is_file():
        return PW_FFMPEG, "vp8"
    raise SystemExit("no ffmpeg available to compress the recording")


def transcode(ffmpeg: str, codec: str, src: Path, dst: Path) -> int:
    """Scale to 960 wide, 24fps, no audio; step quality down until under
    budget. Returns the final byte size."""
    if codec == "vp9":
        attempts = [["-c:v", "libvpx-vp9", "-crf", str(crf), "-b:v", "0"]
                    for crf in (42, 47, 52)]
    else:
        attempts = [["-c:v", "libvpx", "-crf", "30", "-b:v", bv,
                     "-qmin", "4", "-qmax", "50"]
                    for bv in ("480k", "380k", "300k")]
    for extra in attempts:
        cmd = [ffmpeg, "-y", "-i", str(src),
               "-vf", "scale=960:-2", "-r", "24", "-an",
               *extra, "-deadline", "good", "-cpu-used", "2", str(dst)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        size = dst.stat().st_size
        if size <= VIDEO_BUDGET:
            return size
    return dst.stat().st_size


def make_poster(raw: Path, dst: Path) -> int:
    from PIL import Image
    img = Image.open(raw).convert("RGB")
    w = 960
    h = round(img.height * w / img.width)
    img = img.resize((w, h), Image.LANCZOS)
    for q in (80, 72, 64, 55):
        img.save(dst, "JPEG", quality=q, optimize=True, progressive=True)
        if dst.stat().st_size <= POSTER_BUDGET:
            break
    return dst.stat().st_size


# --------------------------------------------------------------------- main --
def main() -> None:
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    if WORK.exists():
        shutil.rmtree(WORK)
    DATA_DIR.mkdir(parents=True)
    video_dir = WORK / "video"
    video_dir.mkdir(parents=True)
    poster_raw = WORK / "poster_raw.jpg"

    proc = start_server()
    try:
        workspace = signup()
        print(f"workspace: {workspace.split('?')[0]}")
        raw = film(workspace, video_dir, poster_raw)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print(f"raw recording: {raw} ({raw.stat().st_size} bytes)")
    ffmpeg, codec = pick_ffmpeg()
    OUT_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    vsize = transcode(ffmpeg, codec, raw, OUT_VIDEO)
    psize = make_poster(poster_raw, OUT_POSTER)

    print(f"{OUT_VIDEO}  {vsize} bytes  (codec {codec}, budget {VIDEO_BUDGET})")
    print(f"{OUT_POSTER}  {psize} bytes  (budget {POSTER_BUDGET})")
    if vsize > VIDEO_BUDGET:
        print("WARNING: video is over budget")
    if psize > POSTER_BUDGET:
        print("WARNING: poster is over budget")


if __name__ == "__main__":
    main()
