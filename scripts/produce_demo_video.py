#!/usr/bin/env python3
"""
produce_demo_video.py -- cut the raw TrustOps screen capture into a PRODUCED,
edited, silent film: title card, act cards, hard cuts, punch-in zooms,
kinetic lower-third captions, cross-dissolves, a running progress bar and a
closing stat card.

    .venv/bin/python scripts/produce_demo_video.py

Reads   site/img/demo.webm            (VP8, 960x600, 24fps, 737 frames, silent)
Writes  site/img/demo_edit.mp4        (H.264 High, yuv420p, faststart)  <- primary
        site/img/demo_edit.webm       (VP9 in WebM)                     <- fallback
        site/img/demo_edit_poster.jpg (960x600, q82)

WHY IT IS BUILT THIS WAY
------------------------
Every composite is done in PIL, one frame at a time, and handed to ffmpeg as
raw RGB24 on stdin.  Nothing is drawn by an ffmpeg filter.  That is deliberate:
it gives pixel-exact control over the brand typography (Newsreader / Archivo /
Fragment Mono, loaded straight out of the .woff2 files) and over the easing of
every zoom, which drawtext+zoompan cannot do.

THE EDIT
--------
Source beats were measured from the capture, not guessed (see BEATS below).
The timeline is the SHOTS table -- it is plain data, edit it and re-run.

  frames are 24fps.  A footage shot names a source frame `src` and animates a
  crop rectangle from `start` to `end`, each being (centre_x, centre_y, zoom).
  The crop is always exactly 8:5 so nothing is ever stretched.

MOVE AND HOLD  (the whole point of the second cut)
--------------------------------------------------
The first cut ran 22s over 13 beats -- every zoom arrived and immediately cut,
so the film read as motion rather than information.  Nothing here is a beat you
can read in 1.4 seconds.

So a shot is now two phases, not one:

    move   ~1.8s   the camera eases from `start` to `end`, and the source
                   footage advances 1:1 so live events (the seed landing, the
                   button click, the run finishing) play inside the move.
    hold   ~3.2s   t is pinned at 1.0 AND the source frame is pinned at
                   src+srcn-1.  The crop rectangle is therefore byte-identical
                   frame to frame; the only thing that changes is the caption
                   and the 2px progress bar.  The stillness is real, not slow.

`srcn` is how many source frames the move is allowed to eat, clamped to the
STATIC window listed in BEATS -- a 44-frame move over a 34-frame static window
would scroll off the beat, so the footage freezes first and the camera keeps
easing to its mark.

Cards hold the same way: they finish animating, then sit.
"""

from __future__ import annotations

import io
import math
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_VIDEO = os.path.join(ROOT, "site", "img", "demo.webm")
OUT_DIR = os.path.join(ROOT, "site", "img")
OUT_MP4 = os.path.join(OUT_DIR, "demo_edit.mp4")
OUT_WEBM = os.path.join(OUT_DIR, "demo_edit.webm")
OUT_POSTER = os.path.join(OUT_DIR, "demo_edit_poster.jpg")
FONT_DIR = os.path.join(ROOT, "trustops", "assets", "fonts")

W, H = 960, 600
FPS = 24

# --------------------------------------------------------------------------
# Brand palette (exact values from the TrustOps design tokens)
# --------------------------------------------------------------------------

INK = (0x14, 0x14, 0x16)  # page
SUNKEN = (0x0E, 0x0E, 0x10)  # deepest ground, used for act cards
CARD = (0x1A, 0x1A, 0x1D)
BONE = (0xE8, 0xE8, 0xE4)  # primary text
SECOND = (0xB4, 0xB4, 0xAE)
TERTIARY = (0x8F, 0x8F, 0x88)
SIGNAL = (0xB7, 0xC4, 0xFF)  # release / accent
REFUSAL = (0xD9, 0x78, 0x62)
OK = (0x9B, 0xC4, 0x9C)
WARN = (0xD9, 0xB3, 0x6A)

# --------------------------------------------------------------------------
# BEATS -- measured from the source by decoding frames and looking at them.
# Motion analysis (mean abs inter-frame delta) gave these STATIC windows, so
# every punch-in sits inside a window where the page is not scrolling:
#
#   f  90-f123  the seed click lands; "Seeded 13 sample documents" pops in
#   f152-f190  the full 13-document list, ATTESTED / APPROVED chips
#   f210-f251  the ten questions; RUN THE QUESTIONNAIRE is clicked (~f220)
#   f300-f368  the RUN COMPLETE card is up and held
#   f388-f427  report top: 60.0% dial + stat tiles
#   f446-f491  refusal stack bar: 1 CONTRADICTION / 2 STALE / 1 LEGAL
#   f534-f580  02 EVIDENCE INTEGRITY: stale + contradiction cards
#   f634-f673  the question ledger; H-05 CONTRADICTION provenance
#
# Captions below are true to what is on the screen at that exact moment.
# --------------------------------------------------------------------------

# transition into the shot: "cut" | "wipe" (footage wipes over the act card)
#                           | "dissolve" (blended with the previous shot's tail)

# Standard lengths.  MOVE+HOLD = 122 frames = 5.08s per footage shot.
MOVE = 44   # 1.83s of eased camera
HOLD = 78   # 3.25s of dead-still frame at the end mark
DISS = 12   # cross-dissolve
WIPE = 12   # graphic wipe off an act card

# Nine footage shots became six.  Three are gone entirely, not shortened, and
# their captions went with them -- a caption that outlives its shot points at
# nothing:
#   src=152  the tilt down the document list.  The punch at src=90 now settles
#            holding the 13/20 counter AND seven ATTESTED rows, so the tilt
#            said nothing the shot before it had not already said.
#            (dropped caption: "EVERY FILE ATTESTED AND APPROVED")
#   src=446  the stat tiles.  388, 446 and 464 were three separate punch-ins
#            into ONE static page view -- precisely the "just transitions"
#            read.  The dial punch already carries VALID / 0.09s in frame.
#            (dropped caption: "AUDIT CHAIN VALID, 0.09s CYCLE")
#   src=464  the refusal stack seen from the report-top window.  Merged into
#            the 534 shot, which frames the same stack bar (see the note on
#            that shot for why the 446 window cannot work).  The evidence
#            integrity cards the 534 shot used to be about are now the bottom
#            third of that same frame, so nothing was lost.
#            (dropped caption: "TAINTED SOURCES, QUARANTINED" -- src=632 shows
#            an actual ledger row naming POL-RET-001 / POL-RET-002 as the
#            tainted sources, which is the same point made concretely.)

SHOTS = [
    # --- OPENING ---------------------------------------------------------
    # title composition is finished at i=32; the rest is the hold
    dict(kind="title", n=106),

    # --- ACT 01 : EVIDENCE ----------------------------------------------
    dict(kind="act", n=62, num="01", name="EVIDENCE",
         sub="Thirteen documents, seeded in one click"),
    # the seed click lands, "Seeded 13 sample documents" pops in, and the punch
    # settles holding the 13/20 counter and the first seven ATTESTED rows
    dict(kind="footage", src=90, srcn=34, trans="wipe", wipe=WIPE,
         start=(480, 300, 1.00), end=(310, 412, 1.60),
         caption="13 DOCUMENTS, EVERY ONE ATTESTED"),

    # --- ACT 02 : RUN ----------------------------------------------------
    dict(kind="act", n=62, num="02", name="RUN",
         sub="Ten questions, one click"),
    # the ten questions, then the button is pressed and the run starts.
    # The end mark must hold H-03..H-10 AND the button AND the "Running:"
    # line -- the caption says "ten questions", so ten questions have to be in
    # frame when it finishes typing.  x 88..699 keeps the question text; the
    # crop bottoms out at src y=396 so "Running:" clears the caption bar.
    dict(kind="footage", src=210, srcn=42, trans="wipe", wipe=WIPE,
         start=(480, 300, 1.00), end=(394, 211, 1.57),
         caption="TEN QUESTIONS, ONE CLICK"),
    # dissolve = time passing while the run gates; land on the verdict card
    dict(kind="footage", src=300, srcn=MOVE, trans="dissolve", diss=DISS,
         start=(480, 300, 1.18), end=(330, 280, 1.75),
         caption="10 QUESTIONS. 0 DELIVERED. 4 REFUSED."),

    # --- ACT 03 : VERDICTS ----------------------------------------------
    dict(kind="act", n=62, num="03", name="VERDICTS",
         sub="Four refused, every gap named"),
    # push onto the coverage dial
    dict(kind="footage", src=388, srcn=40, trans="wipe", wipe=WIPE,
         start=(480, 300, 1.00), end=(280, 430, 2.00),
         caption="60.0% CITED COVERAGE"),
    # pull back off the CONTRADICTION block to reveal the whole refusal stack,
    # so the caption's three numbers are all on screen when it finishes typing.
    #
    # This uses the 534 window, not the 446 one, for a hard geometric reason.
    # The stack bar spans x 76..884, so showing all three segments caps the
    # zoom at 960/808 = 1.19.  In the 446 window the bar sits at y 500..533,
    # and at zoom <= 1.19 no crop can lift it clear of the lower third -- the
    # caption bar would sit straight across the numbers it is counting.  By
    # the 534 window the page has scrolled and the bar is at y 283..315, which
    # lands mid-frame with room to spare.
    #
    # Dissolve, not a cut: same page, overlapping framing -- a hard cut there
    # reads as a glitch rather than as a deliberate re-frame.
    dict(kind="footage", src=534, srcn=MOVE, trans="dissolve", diss=DISS,
         start=(220, 300, 2.10), end=(480, 341, 1.16),
         caption="1 CONTRADICTION, 2 STALE, 1 LEGAL"),

    # --- ACT 04 : THE REPORT --------------------------------------------
    dict(kind="act", n=62, num="04", name="THE REPORT",
         sub="Every refusal shows its sources"),
    # push into the one ledger row that refused and sit on its provenance:
    # "No answer released", the two conflicting approved sources, and the
    # "no citation released" stamp.  This is the whole thesis in one frame,
    # so it gets the longest settle of any shot in the film.
    # Caption names the CONTRADICTION chip and the italic verdict line, both
    # of which are in frame.  It does NOT name "H-05": at this zoom the row
    # identifier is off to the left, and a caption must be true to the frame
    # it is sitting on.
    dict(kind="footage", src=632, srcn=42, trans="wipe", wipe=WIPE,
         hold=90,
         start=(478, 280, 1.15), end=(655, 245, 2.05),
         caption="CONTRADICTION: NO ANSWER RELEASED"),

    # --- CLOSING ---------------------------------------------------------
    # finished at i=34, tail fade eats the last 8: 98 frames (4.08s) of the
    # three numbers standing still, undimmed
    dict(kind="close", n=140, trans="dissolve", diss=DISS),
]


def normalise(shots):
    """Footage shots are declared as move+hold, not as a raw length."""
    for s in shots:
        if s["kind"] == "footage":
            s.setdefault("move", MOVE)
            s.setdefault("hold", HOLD)
            s.setdefault("srcn", s["move"])
            if s["srcn"] > s["move"]:
                raise SystemExit(f"srcn>{s['move']} for src={s['src']}")
            s["n"] = s["move"] + s["hold"]
    return shots


normalise(SHOTS)

TITLE_EYEBROW = "RECORDED LIVE / NOTHING STAGED"
TITLE_HEAD = "One run, start to finish."

CLOSE_COLUMNS = [
    ("10", "QUESTIONS", BONE),
    ("4", "REFUSED, GAPS NAMED", REFUSAL),
    ("0", "UNCITED ANSWERS RELEASED", OK),
]
CLOSE_WORDMARK = "TrustOps"
CLOSE_LINE = "EVERY ANSWER CITED, OR REFUSED."

# frames of fade-to-ink at the very end so the loop back to frame 0 is soft
TAIL_FADE = 8

# Encoder settings.  The budget is 2.6 MB for the MP4; at crf 26 the 50s cut
# landed at 1.62 MB, which left a megabyte of quality on the table.  This film
# is 50 seconds of small UI type that the viewer is being asked to READ, and
# crf 23 sharpens the caption and screenshot edges for ~0.6 MB.  Most of the
# runtime is frozen frames, which cost almost nothing at any crf, so the extra
# bits go where they are wanted -- the moves and the type.
X264_CRF = 23
# VP9 rather than VP8: at crf 42 it is visually indistinguishable from the
# H.264 master on the caption frames and lands at 0.95MB against VP8's 1.68MB.
# This is only a fallback source (Safari and Chrome both take the MP4), so
# size matters more than the last few dB.
VP9_CRF = "42"

# --------------------------------------------------------------------------
# ffmpeg
# --------------------------------------------------------------------------


def find_ffmpeg() -> str:
    """Prefer the full static build from imageio-ffmpeg (has libx264); the
    system build in this image is compiled --disable-everything."""
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if os.path.exists(exe):
            return exe
    except Exception:
        pass
    for cand in ("/opt/pw-browsers/ffmpeg-1011/ffmpeg-linux", shutil.which("ffmpeg")):
        if cand and os.path.exists(cand):
            return cand
    raise SystemExit("no ffmpeg found")


FFMPEG = find_ffmpeg()


def ffmpeg_has(kind: str, name: str) -> bool:
    out = subprocess.run([FFMPEG, f"-{kind}"], capture_output=True, text=True).stdout
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.strip())


# --------------------------------------------------------------------------
# Fonts -- the brand faces ship as .woff2; PIL cannot read woff2, so decompress
# them to TTF in memory with fontTools.  Each size needs its own BytesIO.
# --------------------------------------------------------------------------

_FONT_TTF: dict[str, bytes] = {}


def _ttf_bytes(name: str) -> bytes:
    if name not in _FONT_TTF:
        from fontTools.ttLib import TTFont

        f = TTFont(os.path.join(FONT_DIR, f"{name}.woff2"))
        f.flavor = None
        buf = io.BytesIO()
        f.save(buf)
        _FONT_TTF[name] = buf.getvalue()
    return _FONT_TTF[name]


_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """name in {news (Newsreader, display), arch (Archivo, body),
    mono (Fragment Mono, labels)}.  Subset faces -- plain ASCII only."""
    key = (name, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(io.BytesIO(_ttf_bytes(name)), size)
    return _FONT_CACHE[key]


# --------------------------------------------------------------------------
# Text helpers.  PIL has no letter-spacing, so tracked text is drawn one
# character at a time with extra advance -- which is how the site sets its
# mono eyebrows and labels.
# --------------------------------------------------------------------------


def tracked_width(text: str, fnt, track: float) -> float:
    if not text:
        return 0.0
    return sum(fnt.getlength(c) + track for c in text) - track


def draw_tracked(dr, xy, text, fnt, fill, track: float = 0.0, alpha: int = 255):
    x, y = xy
    col = fill if alpha >= 255 else fill + (alpha,)
    if alpha < 255 and len(col) == 3:
        col = fill + (alpha,)
    for c in text:
        if c != " ":
            dr.text((x, y), c, font=fnt, fill=col)
        x += fnt.getlength(c) + track
    return x


def ease(t: float) -> float:
    """cubic ease-in-out, the standard camera-move curve"""
    t = min(1.0, max(0.0, t))
    return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2


def ease_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - pow(1 - t, 3)


def mix(a, b, t):
    t = min(1.0, max(0.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# --------------------------------------------------------------------------
# Source frames
# --------------------------------------------------------------------------


def load_source_frames(shots) -> dict[int, Image.Image]:
    """Decode the source once as raw RGB24 and keep only the frames the shot
    list actually asks for.  Streaming keeps peak memory to the kept set."""
    wanted = set()
    for s in shots:
        if s["kind"] == "footage":
            wanted.update(range(s["src"], s["src"] + s["srcn"]))
    hi = max(wanted)
    frame_bytes = W * H * 3
    proc = subprocess.Popen(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", SRC_VIDEO,
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes,
    )
    out: dict[int, Image.Image] = {}
    idx = 0
    try:
        while idx <= hi:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            if idx in wanted:
                out[idx] = Image.frombytes("RGB", (W, H), buf)
            idx += 1
    finally:
        # we stop reading early, so tear the decoder down instead of letting it
        # spew "broken pipe" into stderr
        proc.stdout.close()
        proc.terminate()
        proc.wait()
    missing = wanted - set(out)
    if missing:
        raise SystemExit(f"source is too short; missing frames {sorted(missing)[:5]}...")
    print(f"  decoded {len(out)} source frames of {idx} scanned")
    return out


def crop_zoom(img: Image.Image, cx: float, cy: float, zoom: float) -> Image.Image:
    """Crop an exactly-8:5 window around (cx, cy) at `zoom` and blow it back up
    to full frame.  Clamped to the image so a punch never runs off the edge,
    and rounded to ints so the rectangle never wobbles sub-pixel."""
    zoom = max(1.0, zoom)
    cw = int(round(W / zoom))
    ch = int(round(cw * H / W))  # exact 8:5, no distortion
    cw = min(cw, W)
    ch = min(ch, H)
    x = int(round(cx - cw / 2))
    y = int(round(cy - ch / 2))
    x = max(0, min(W - cw, x))
    y = max(0, min(H - ch, y))
    box = img.crop((x, y, x + cw, y + ch))
    if (cw, ch) == (W, H):
        return box
    return box.resize((W, H), Image.LANCZOS)


# --------------------------------------------------------------------------
# Chrome: lower-third captions and the progress bar
# --------------------------------------------------------------------------

CAP_Y = 512
CAP_H = 46
CAP_PAD = 44


CAP_IN_AT, CAP_IN_LEN = 5, 9
CAP_OUT_LEN = 9
# a caption must stand fully typed and fully visible for at least this long
# before it drops -- 62 frames = 2.58s.  If the text is long enough that the
# deliberate type-on would eat into that, the type-on is compressed, not the
# hold: an unread caption is the failure mode we are fixing.
CAP_MIN_HOLD = 62


def caption_type_window(text: str, n: int) -> tuple[int, int]:
    """(first frame that draws a character, frames spent typing)."""
    start = CAP_IN_AT + CAP_IN_LEN - 3
    out_at = n - CAP_OUT_LEN
    # ~1.35 frames per character == about 18 characters a second.  The first
    # cut ran at 43 c/s, which is why it read as flicker.
    want = max(14, int(round(len(text) * 1.35)))
    return start, max(10, min(want, out_at - start - CAP_MIN_HOLD))


def draw_caption(img: Image.Image, text: str, i: int, n: int):
    """A lower-third bar that slides up, types its line on, holds, and drops
    away before the cut.  Mono, uppercase, tracked -- the site's label voice."""
    IN_AT, IN_LEN = CAP_IN_AT, CAP_IN_LEN
    OUT_LEN = CAP_OUT_LEN
    out_at = n - OUT_LEN
    if i < IN_AT:
        return
    if i < IN_AT + IN_LEN:
        prog = ease_out((i - IN_AT) / IN_LEN)
    elif i >= out_at:
        prog = 1.0 - ease((i - out_at) / OUT_LEN)
    else:
        prog = 1.0
    if prog <= 0.01:
        return

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    off = int(round((1 - prog) * (CAP_H + 8)))
    top = CAP_Y + off
    a = int(round(prog * 224))
    dr.rectangle([0, top, W, top + CAP_H], fill=INK + (a,))
    dr.rectangle([0, top, W, top], fill=SIGNAL + (int(a * 0.95),))

    # type-on: linear, like a real typewriter -- easing makes the last few
    # characters crawl and the line reads as truncated for most of the shot
    type_start, type_len = caption_type_window(text, n)
    if i >= type_start + type_len or i >= out_at:
        shown = len(text)
    else:
        shown = int(len(text) * max(0.0, (i - type_start) / type_len))
    vis = text[:shown]

    fnt = font("mono", 15)
    ty = top + (CAP_H - 15) // 2 - 3
    # signal tick before the line
    dr.rectangle([CAP_PAD - 18, ty + 5, CAP_PAD - 12, ty + 11], fill=SIGNAL + (a,))
    xend = draw_tracked(dr, (CAP_PAD, ty), vis, fnt, BONE, track=2.2, alpha=a)
    # blinking caret while typing
    if shown < len(text) and (i // 4) % 2 == 0:
        dr.rectangle([xend, ty + 2, xend + 7, ty + 15], fill=SIGNAL + (a,))

    img.alpha_composite(layer) if img.mode == "RGBA" else \
        img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))


def draw_progress(img: Image.Image, i: int, total: int):
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, H - 2, W, H], fill=(0x2A, 0x2A, 0x30))
    w = int(round(W * (i + 1) / total))
    if w > 0:
        dr.rectangle([0, H - 2, w, H], fill=SIGNAL)


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------


def render_title(i: int, n: int) -> Image.Image:
    """Eyebrow fades in, a signal rule draws across, the headline wipes on."""
    img = Image.new("RGB", (W, H), INK)
    dr = ImageDraw.Draw(img)

    # a very soft vertical lift so the flat ink is not dead
    for y in range(0, H, 2):
        t = y / H
        dr.rectangle([0, y, W, y + 2], fill=mix((0x17, 0x17, 0x1A), SUNKEN, t))

    x0, x1 = 88, W - 88

    # eyebrow
    a = int(255 * ease_out(i / 9))
    if a > 0:
        f = font("mono", 13)
        draw_over(img, lambda d: draw_tracked(d, (x0, 214), TITLE_EYEBROW, f,
                                              TERTIARY, track=3.6, alpha=a))

    # signal rule draws left to right
    rp = ease((i - 5) / 16)
    if rp > 0:
        dr.rectangle([x0, 250, x0 + int((x1 - x0) * rp), 250], fill=SIGNAL)

    # headline wipes on from the left behind a soft edge
    hp = ease((i - 9) / 20)
    if hp > 0:
        head = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        hd = ImageDraw.Draw(head)
        hd.text((x0, 286), TITLE_HEAD, font=font("news", 58), fill=BONE + (255,))
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        edge = int(x0 + (x1 - x0 + 60) * hp)
        md.rectangle([0, 0, edge - 26, H], fill=255)
        for k in range(26):  # feathered wipe edge
            md.rectangle([edge - 26 + k, 0, edge - 26 + k, H],
                         fill=int(255 * (1 - k / 26)))
        head.putalpha(Image.composite(head.split()[3], Image.new("L", (W, H), 0), mask))
        img.paste(Image.alpha_composite(img.convert("RGBA"), head).convert("RGB"), (0, 0))

    # small mono footer, fades in last
    a2 = int(255 * ease_out((i - 20) / 12))
    if a2 > 0:
        f = font("mono", 11)
        draw_over(img, lambda d: draw_tracked(d, (x0, 392), "TRUSTOPS DESK / EVIDENCE GATED ANSWER ENGINE",
                                              f, (0x60, 0x60, 0x5C), track=2.6, alpha=a2))
    return img


def render_act(i: int, n: int, num: str, name: str, sub: str) -> Image.Image:
    """Graphic, quick.  Big tracked number, rule, one line of Archivo."""
    img = Image.new("RGB", (W, H), SUNKEN)
    dr = ImageDraw.Draw(img)
    x0 = 88
    p = ease_out(i / 8)

    # the number slides in a few px and settles
    dx = int(round((1 - p) * 18))
    a = int(255 * p)

    fnum = font("mono", 15)
    label = f"{num}  /  {name}"
    draw_over(img, lambda d: draw_tracked(d, (x0 + dx, 250), label, fnum, SIGNAL,
                                          track=5.0, alpha=a))

    rp = ease((i - 2) / 12)
    if rp > 0:
        wr = int((W - 176) * rp)
        dr.rectangle([x0, 284, x0 + wr, 284], fill=(0x33, 0x33, 0x3A))

    a2 = int(255 * ease_out((i - 4) / 9))
    if a2 > 0:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.text((x0 + int((1 - a2 / 255) * 14), 306), sub,
                font=font("arch", 27), fill=BONE + (a2,))
        img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))
    return img


def render_close(i: int, n: int) -> Image.Image:
    """Three columns of outcome, the wordmark, one mono line."""
    img = Image.new("RGB", (W, H), INK)
    dr = ImageDraw.Draw(img)
    for y in range(0, H, 2):
        dr.rectangle([0, y, W, y + 2], fill=mix((0x17, 0x17, 0x1A), SUNKEN, y / H))

    x0 = 76
    colw = (W - 152) // 3

    rp = ease(i / 14)
    if rp > 0:
        dr.rectangle([x0, 196, x0 + int((W - 152) * rp), 196], fill=SIGNAL)

    fnum = font("news", 74)
    flab = font("mono", 11)
    for c, (val, lab, col) in enumerate(CLOSE_COLUMNS):
        p = ease_out((i - 4 - c * 5) / 12)
        if p <= 0:
            continue
        a = int(255 * p)
        cx = x0 + c * colw
        dy = int(round((1 - p) * 12))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.text((cx, 232 + dy), val, font=fnum, fill=col + (a,))
        img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))
        # label can run to two lines inside the column
        words = lab.split(", ")
        ly = 336
        for wline in words:
            draw_over(img, lambda d, t=wline, yy=ly, xx=cx: draw_tracked(
                d, (xx, yy), t, flab, TERTIARY, track=2.2, alpha=a))
            ly += 17
        if c:
            dr.rectangle([cx - 22, 236, cx - 22, 352], fill=(0x2C, 0x2C, 0x32))

    # wordmark + line
    p = ease_out((i - 20) / 14)
    if p > 0:
        a = int(255 * p)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.text((x0, 414), CLOSE_WORDMARK, font=font("news", 42), fill=BONE + (a,))
        img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))
        f = font("mono", 13)
        draw_over(img, lambda d: draw_tracked(d, (x0, 478), CLOSE_LINE, f,
                                              SIGNAL, track=3.4, alpha=a))
    return img


def draw_over(img: Image.Image, fn):
    """Run a drawing callback on an RGBA overlay and composite it, so alpha
    actually blends instead of being ignored on an RGB canvas."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fn(ImageDraw.Draw(layer))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))


# --------------------------------------------------------------------------
# Shot rendering
# --------------------------------------------------------------------------


def render_shot(shot, src_frames, prev_frame) -> list[Image.Image]:
    n = shot["n"]
    kind = shot["kind"]
    frames: list[Image.Image] = []

    for i in range(n):
        if kind == "title":
            img = render_title(i, n)
        elif kind == "act":
            img = render_act(i, n, shot["num"], shot["name"], shot["sub"])
        elif kind == "close":
            img = render_close(i, n)
        else:
            # ease() clamps, so for i >= move-1 the crop rectangle is EXACTLY
            # the end mark -- same ints, same box -- and the source index is
            # pinned too.  Those frames are byte-identical apart from the
            # caption and the progress bar.  That is the hold.
            t = ease(i / max(1, shot["move"] - 1))
            sx, sy, sz = shot["start"]
            ex, ey, ez = shot["end"]
            img = crop_zoom(
                src_frames[shot["src"] + min(i, shot["srcn"] - 1)],
                sx + (ex - sx) * t, sy + (ey - sy) * t, sz + (ez - sz) * t,
            )
            if shot.get("caption"):
                draw_caption(img, shot["caption"], i, n)
        frames.append(img)

    # horizontal wipe: the footage sweeps in over the outgoing act card, with a
    # 2px signal blade on the leading edge -- the classic hard graphic wipe.
    wn = shot.get("wipe", 0)
    if shot.get("trans") == "wipe" and wn and prev_frame is not None:
        for i in range(min(wn, n)):
            p = ease((i + 1) / wn)
            edge = int(round(W * p))
            comp = prev_frame.copy()
            if edge > 0:
                comp.paste(frames[i].crop((0, 0, edge, H)), (0, 0))
            if 0 < edge < W:
                ImageDraw.Draw(comp).rectangle([edge - 2, 0, edge, H], fill=SIGNAL)
            frames[i] = comp
    return frames


# --------------------------------------------------------------------------
# Timeline assembly + encode
# --------------------------------------------------------------------------


def timeline_length(shots) -> int:
    total = sum(s["n"] for s in shots)
    for s in shots:
        if s.get("trans") == "dissolve":
            total -= s.get("diss", DISS)
    return total


class Encoder:
    """Fans one raw RGB24 stream out to every encoder we can build."""

    def __init__(self, total: int):
        self.total = total
        self.i = 0
        self.procs = []
        self.poster: Image.Image | None = None

        common = ["-hide_banner", "-loglevel", "error", "-y",
                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                  "-r", str(FPS), "-i", "pipe:0", "-an"]  # -an: never any audio

        if ffmpeg_has("encoders", "libx264"):
            self.procs.append(("mp4", subprocess.Popen(
                [FFMPEG, *common, "-c:v", "libx264", "-profile:v", "high",
                 "-pix_fmt", "yuv420p", "-crf", str(X264_CRF), "-preset", "slower",
                 "-g", "48", "-movflags", "+faststart", OUT_MP4],
                stdin=subprocess.PIPE)))
        else:
            print("  !! no libx264 -- skipping MP4")

        self.procs.append(("webm", subprocess.Popen(
            [FFMPEG, *common, "-c:v", "libvpx-vp9", "-crf", VP9_CRF, "-b:v", "0",
             "-row-mt", "1", "-cpu-used", "2",
             "-pix_fmt", "yuv420p", OUT_WEBM],
            stdin=subprocess.PIPE)))

    def write(self, img: Image.Image, poster: bool = False):
        if img.mode != "RGB":
            img = img.convert("RGB")
        # global tail fade so the loop back to the title card is not a slam
        left = self.total - self.i
        if left <= TAIL_FADE:
            k = 1.0 - (left - 1) / TAIL_FADE * 0.72 - 0.28
            img = Image.blend(img, Image.new("RGB", (W, H), INK), min(0.7, max(0.0, k)))
        draw_progress(img, self.i, self.total)
        if poster and self.poster is None:
            self.poster = img.copy()
        data = img.tobytes()
        for _, p in self.procs:
            p.stdin.write(data)
        self.i += 1

    def close(self):
        for _, p in self.procs:
            p.stdin.close()
        for name, p in self.procs:
            if p.wait() != 0:
                raise SystemExit(f"{name} encoder failed")


def main() -> int:
    if not os.path.exists(SRC_VIDEO):
        raise SystemExit(f"missing source {SRC_VIDEO}")
    print(f"ffmpeg: {FFMPEG}")

    total = timeline_length(SHOTS)
    print(f"timeline: {len(SHOTS)} shots, {total} frames, {total / FPS:.2f}s @ {FPS}fps")

    print("decoding source...")
    src_frames = load_source_frames(SHOTS)

    enc = Encoder(total)
    # frame chosen for the poster: deep in the RUN COMPLETE hold, camera
    # settled, caption fully typed on -- a composed frame, not a screenshot.
    poster_shot, poster_i = 5, 76

    pending_tail: list[Image.Image] = []
    prev_frame: Image.Image | None = None

    for si, shot in enumerate(SHOTS):
        frames = render_shot(shot, src_frames, prev_frame)

        off = 0  # frames of this shot already consumed by an incoming dissolve
        if shot.get("trans") == "dissolve" and pending_tail:
            k = min(len(pending_tail), shot.get("diss", DISS), len(frames))
            for j in range(k):
                t = (j + 1) / (k + 1)
                enc.write(Image.blend(pending_tail[-k + j], frames[j], t))
            frames = frames[k:]
            off = k
            pending_tail = []
        elif pending_tail:
            for f in pending_tail:
                enc.write(f)
            pending_tail = []

        nxt = SHOTS[si + 1] if si + 1 < len(SHOTS) else None
        tail_n = nxt.get("diss", DISS) if (nxt and nxt.get("trans") == "dissolve") else 0
        tail_n = min(tail_n, len(frames))

        body = frames[: len(frames) - tail_n] if tail_n else frames
        for fi, f in enumerate(body):
            enc.write(f, poster=(si == poster_shot and off + fi == poster_i))
        pending_tail = frames[len(frames) - tail_n:] if tail_n else []
        prev_frame = frames[-1] if frames else prev_frame

    for f in pending_tail:
        enc.write(f)
    enc.close()

    if enc.i != total:
        print(f"  !! wrote {enc.i} frames, predicted {total}")

    if enc.poster is not None:
        enc.poster.save(OUT_POSTER, "JPEG", quality=82, optimize=True,
                        progressive=True, subsampling=1)

    print()
    for path in (OUT_MP4, OUT_WEBM, OUT_POSTER):
        if os.path.exists(path):
            print(f"  {os.path.relpath(path, ROOT):34s} {os.path.getsize(path):>9,d} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
