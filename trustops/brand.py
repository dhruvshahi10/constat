"""Brand system: one palette, one type set, one component vocabulary.

Colours are the owner's Claude Design system (project f0b00150), adopted
verbatim from dhruv-portfolio/design-system/tokens/colors.css. That export
already carries GRC status semantics (ok / warn / critical / info) which the
portfolio does not use; this is the product they were named for.

Typefaces ship with the package as subset woff2 and are inlined as data URIs.
Rationale: a run report is an audit artefact that must render identically
years later, on a machine that may have no network. A webfont CDN link makes
the working paper depend on a third party staying up, which is exactly the
dependency this product exists to remove. If the files are missing the stacks
degrade to system faces and nothing breaks.

Copy rule inherited from the brand: no em dashes and no en dashes anywhere in
rendered copy. scripts/copy-gate.mjs in the portfolio enforces it mechanically.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

FONT_DIR = Path(__file__).parent / "assets" / "fonts"

# (family, file, css weight range)
_FACES = [
    ("Newsreader", "news.woff2", "200 800"),
    ("Archivo", "arch.woff2", "100 900"),
    ("Fragment Mono", "mono.woff2", "400"),
]


@lru_cache(maxsize=1)
def font_faces() -> str:
    """@font-face rules with the subset faces inlined. Empty if unavailable."""
    out = []
    for family, filename, weight in _FACES:
        path = FONT_DIR / filename
        if not path.is_file():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        out.append(
            f"@font-face{{font-family:'{family}';"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');"
            f"font-weight:{weight};font-style:normal;font-display:swap}}"
        )
    return "\n".join(out)


TOKENS = """
:root{
--ink-0:#0E0E10;--ink-1:#141416;--ink-2:#1A1A1D;--ink-3:#222226;--ink-4:#2B2B30;
--bone-1:#E8E8E4;--bone-2:#B4B4AE;--bone-3:#85857E;--bone-4:#56564F;
--signal:#B7C4FF;--signal-bright:#CFD8FF;--signal-deep:#6E7CC3;
--signal-wash:rgba(183,196,255,0.09);--signal-ink:#14151F;
--status-ok:#9BC49C;--status-warn:#D9B36A;--status-critical:#D97862;--status-info:#8FB0BE;
--status-ok-wash:rgba(155,196,156,0.10);--status-warn-wash:rgba(217,179,106,0.12);
--status-critical-wash:rgba(217,120,98,0.12);--status-info-wash:rgba(143,176,190,0.10);
--line-1:rgba(232,232,228,0.10);--line-2:rgba(232,232,228,0.18);--line-3:rgba(232,232,228,0.32);
--line-signal:rgba(183,196,255,0.45);
--surface-page:var(--ink-1);--surface-sunken:var(--ink-0);--surface-card:var(--ink-2);
--surface-raised:var(--ink-3);
--text-primary:var(--bone-1);--text-secondary:var(--bone-2);--text-tertiary:var(--bone-3);
--text-faint:var(--bone-4);--focus-ring:var(--signal);
--font-display:'Newsreader',Georgia,serif;
--font-sans:'Archivo',Helvetica,Arial,sans-serif;
--font-mono:'Fragment Mono','Courier New',monospace;
--tracking-caps:0.16em;--radius-1:2px;--radius-2:4px;
}
"""

BASE = """
*{box-sizing:border-box;margin:0;padding:0}
html{color-scheme:dark}
body{background:var(--surface-page);color:var(--text-primary);font-family:var(--font-sans);
font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;padding:0 0 72px}
.wrap{max-width:1140px;margin:0 auto;padding:0 clamp(18px,4vw,32px)}
h1,h2,h3{font-family:var(--font-display);font-weight:400;letter-spacing:-0.015em;line-height:1.12}
svg{display:block;max-width:100%}
::selection{background:var(--signal);color:var(--signal-ink)}
:focus-visible{outline:1px solid var(--focus-ring);outline-offset:2px}
a{color:var(--signal);text-decoration-color:var(--line-signal);text-underline-offset:3px}

header{border-bottom:1px solid var(--line-2);padding:56px 0 26px;margin-bottom:34px}
.eyebrow{font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.24em;text-transform:uppercase;
color:var(--text-faint);margin-bottom:18px}
.eyebrow b{color:var(--signal);font-weight:400}
h1{font-size:clamp(30px,4.6vw,52px);line-height:1.02}
h1 i{font-style:italic;color:var(--signal)}
.runmeta{margin-top:16px;font-family:var(--font-mono);font-size:11px;line-height:1.9;color:var(--text-tertiary)}
h2{font-size:24px;margin:0}
.seclabel{display:flex;align-items:baseline;gap:14px;margin:52px 0 18px}
.seclabel .idx{font-family:var(--font-mono);font-size:12px;color:var(--signal)}
.seclabel .rule{flex:1;border-bottom:1px solid var(--line-1);align-self:center}
.label{font-family:var(--font-mono);font-size:10.5px;letter-spacing:var(--tracking-caps);
text-transform:uppercase;color:var(--text-tertiary)}
.sub{color:var(--text-secondary);font-size:14px;margin:10px 0 18px;max-width:70ch}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
background:var(--line-1);border:1px solid var(--line-1);border-radius:var(--radius-2);
overflow:hidden;margin:26px 0}
.stat{background:var(--surface-card);padding:18px 16px}
.stat b{display:block;font-family:var(--font-display);font-size:38px;font-weight:300;line-height:1;
letter-spacing:-0.02em;font-variant-numeric:tabular-nums}
.stat span{display:block;margin-top:9px;font-family:var(--font-mono);font-size:10px;
letter-spacing:0.13em;text-transform:uppercase;color:var(--text-tertiary)}
.stat.ok b{color:var(--status-ok)}
.stat.warn b{color:var(--status-warn)}
.stat.bad b{color:var(--status-critical)}
.stat.info b{color:var(--signal)}

.chip{display:inline-flex;align-items:center;gap:7px;padding:4px 9px;border:1px solid var(--line-1);
border-radius:var(--radius-1);font-family:var(--font-mono);font-size:10px;letter-spacing:0.12em;
text-transform:uppercase;white-space:nowrap}
.chip::before{content:"";width:5px;height:5px;background:currentColor;flex:0 0 5px}
.c-ok{color:var(--status-ok);background:var(--status-ok-wash)}
.c-rev{color:var(--status-warn);background:var(--status-warn-wash)}
.c-warn{color:var(--status-critical);background:var(--status-critical-wash)}
.c-info{color:var(--status-info);background:var(--status-info-wash)}
.c-sig{color:var(--signal);background:var(--signal-wash);border-color:var(--line-signal)}

.panel{background:var(--surface-card);border:1px solid var(--line-1);border-left:2px solid var(--status-warn);
border-radius:var(--radius-2);padding:16px 18px;margin-bottom:10px}
.panel h3{font-family:var(--font-mono);font-size:10.5px;letter-spacing:var(--tracking-caps);
text-transform:uppercase;margin-bottom:8px;color:var(--status-warn)}
.panel p{font-size:13.5px;color:var(--text-secondary)}

table{width:100%;border-collapse:collapse;background:var(--surface-card);
border:1px solid var(--line-1);border-radius:var(--radius-2);overflow:hidden}
th{font-family:var(--font-mono);font-size:10px;letter-spacing:0.13em;text-transform:uppercase;
text-align:left;padding:12px;border-bottom:1px solid var(--line-2);color:var(--text-faint)}
td{padding:14px 12px;border-bottom:1px solid var(--line-1);vertical-align:top;font-size:13.5px;
color:var(--text-secondary)}
tr:last-child td{border-bottom:none}
.qid{font-family:var(--font-mono);font-size:11.5px;color:var(--text-primary);white-space:nowrap}
.dom{color:var(--text-faint);font-size:11px;font-family:var(--font-mono)}
.ans{max-width:52ch;color:var(--text-primary)}
.gap{color:var(--status-warn);font-size:12px;margin-top:7px;font-family:var(--font-mono);line-height:1.6}
.prov{margin-top:9px;font-family:var(--font-mono);font-size:10.5px;line-height:1.7;
color:var(--text-tertiary);border-left:2px solid var(--status-ok);padding:3px 0 3px 9px;
background:linear-gradient(90deg,var(--status-ok-wash),transparent 70%)}
.prov.p-warn{border-left-color:var(--status-critical);
background:linear-gradient(90deg,var(--status-critical-wash),transparent 70%)}
.evals td:first-child{font-family:var(--font-mono);font-size:11.5px;color:var(--signal)}
.pass{color:var(--status-ok)}

.cells{display:grid;grid-template-columns:repeat(24,1fr);gap:3px;margin-bottom:12px}
.cell{aspect-ratio:1;border-radius:1px}
.k-del{background:var(--status-ok-wash);box-shadow:inset 0 0 0 1px var(--status-ok)}
.k-rev{background:var(--status-warn-wash);box-shadow:inset 0 0 0 1px var(--status-warn)}
.k-exc{background:var(--status-critical-wash);box-shadow:inset 0 0 0 1px var(--status-critical)}
.latkey{display:flex;flex-wrap:wrap;gap:9px 18px;align-items:center}
.viz{display:grid;gap:28px;grid-template-columns:1fr;align-items:center;margin:26px 0}
@media(min-width:820px){.viz{grid-template-columns:230px 1fr}}
.stackbar{display:flex;height:46px;border-radius:var(--radius-1);overflow:hidden;gap:2px}
.stackbar div{display:flex;align-items:center;justify-content:center;font-family:var(--font-mono);
font-size:10.5px;color:var(--ink-0)}
.sb-r{background:var(--status-warn)}.sb-s{background:var(--status-critical)}
.sb-c{background:var(--status-info)}.sb-l{background:var(--status-ok)}

footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--line-1);
font-family:var(--font-mono);font-size:10.5px;line-height:2;color:var(--text-faint)}
@media(max-width:720px){td:nth-child(2),th:nth-child(2){display:none}.cells{grid-template-columns:repeat(12,1fr)}}
"""


def stylesheet(extra: str = "") -> str:
    """Full stylesheet: inlined faces, tokens, base vocabulary, then extras."""
    return f"{font_faces()}\n{TOKENS}\n{BASE}\n{extra}"


def coverage_dial(pct: float, ceiling: float | None = None) -> str:
    """Donut showing cited coverage, optionally against a reachable ceiling."""
    r, circ = 82, 515.2
    ring = ""
    if ceiling is not None and ceiling > pct:
        ring = (f'<circle cx="110" cy="110" r="{r}" fill="none" stroke="var(--signal-deep)" '
                f'stroke-width="16" opacity="0.4" stroke-dasharray="{circ:.1f}" '
                f'stroke-dashoffset="{circ * (1 - ceiling):.1f}" transform="rotate(-90 110 110)"/>')
    ceil_txt = (f'<text x="110" y="146" text-anchor="middle" class="d-sig">CEILING '
                f'{ceiling * 100:.1f}%</text>') if ceiling is not None else ""
    return f"""<svg viewBox="0 0 220 220" role="img" aria-label="Cited coverage {pct * 100:.1f} percent">
<style>.d-num{{font-family:var(--font-display);font-size:38px;font-weight:300;fill:var(--text-primary)}}
.d-cap{{font-family:var(--font-mono);font-size:9px;fill:var(--text-tertiary);letter-spacing:0.14em}}
.d-sig{{font-family:var(--font-mono);font-size:9px;fill:var(--signal);letter-spacing:0.14em}}</style>
<circle cx="110" cy="110" r="{r}" fill="none" stroke="var(--line-1)" stroke-width="16"/>{ring}
<circle cx="110" cy="110" r="{r}" fill="none" stroke="var(--signal)" stroke-width="16"
 stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ * (1 - pct):.1f}" transform="rotate(-90 110 110)"/>
<text x="110" y="106" text-anchor="middle" class="d-num">{pct * 100:.1f}%</text>
<text x="110" y="126" text-anchor="middle" class="d-cap">CITED COVERAGE</text>{ceil_txt}</svg>"""


_CELL_CLASS = {"DELIVERED": "k-del", "GRC_REVIEW": "k-rev"}


def run_lattice(items: list[tuple[str, str, str]]) -> str:
    """One cell per question. items = (question_id, state, tooltip reason)."""
    cells = "".join(
        f'<div class="cell {_CELL_CLASS.get(state, "k-exc")}" '
        f'title="{qid}: {reason}"></div>'
        for qid, state, reason in items
    )
    return f'<div class="cells">{cells}</div>'
