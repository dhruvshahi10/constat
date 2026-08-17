"""Build marketing/one-pager.html from the brand system.

The one pager used to be a hand-maintained fork of the brand CSS: a copy of
every token and every base rule, pasted into a file no script regenerated. It
had already drifted, and it printed as a white page, because a dark design that
does not ask for its background to survive printing gets its background thrown
away by the browser and left bone-coloured text on white paper. A one pager
that cannot be printed is not a one pager.

This script fixes both. The stylesheet comes from brand.stylesheet(), so the
sheet cannot drift from the product, and PRINT_CSS sets print-color-adjust on
html, body and .sheet so the ink survives the print pipeline.

The PDF is printed here too. It used to be produced by hand, which meant the
committed binary went stale the moment the HTML changed: the rename to Pramana
found a PDF still carrying the old brand in its glyphs, where no text search
could see it. Printing it in the same script that writes the HTML removes that
class of drift. Playwright is optional; without it the HTML is still written
and the PDF step reports that it was skipped.

    .venv/bin/python scripts/build_one_pager.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pramana import brand  # noqa: E402

PRINT_CSS = """
/* Browsers drop background paint when printing unless the document insists.
   Without these three declarations the whole sheet prints as bone text on
   white, which is how this file used to behave. */
html,body,.sheet{-webkit-print-color-adjust:exact;print-color-adjust:exact;
color-adjust:exact}
@page{size:A4;margin:0}
html,body{width:210mm;height:297mm;overflow:hidden;background:var(--surface-page)}
body{padding:0;font-size:10.5pt}
.sheet{width:210mm;height:297mm;padding:12mm 14mm;display:flex;flex-direction:column;
gap:4.6mm;background:var(--surface-page)}
.mast{display:flex;justify-content:space-between;align-items:baseline;
border-bottom:1px solid var(--line-2);padding-bottom:3.6mm}
.wordmark{font-family:var(--font-mono);font-size:12pt;letter-spacing:0.22em;text-transform:uppercase}
.wordmark b{color:var(--signal);font-weight:400;margin-left:-0.22em}
.mast .tag{font-family:var(--font-mono);font-size:7pt;letter-spacing:0.16em;
text-transform:uppercase;color:var(--text-tertiary)}
h1{font-size:22pt;line-height:1.06;letter-spacing:-0.015em}
h1 i{font-style:italic;color:var(--signal)}
.lede{font-size:9.2pt;line-height:1.5;color:var(--text-secondary);max-width:66ch;margin-top:2.2mm}
.row3m{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--line-1);
border:1px solid var(--line-1);border-radius:3px;overflow:hidden}
.mcell{background:var(--surface-card);padding:3.2mm 4mm}
.mcell b{display:block;font-family:var(--font-display);font-weight:300;font-size:15pt;line-height:1.05}
.mcell .ok{color:var(--status-ok)}.mcell .sig{color:var(--signal)}
.mcell span{display:block;font-family:var(--font-mono);font-size:6.4pt;letter-spacing:0.12em;
text-transform:uppercase;color:var(--text-tertiary);margin-top:1.5mm}
.h{font-family:var(--font-mono);font-size:7pt;letter-spacing:0.18em;text-transform:uppercase;
color:var(--text-tertiary);display:flex;gap:3mm;align-items:center}
.h::after{content:"";flex:1;border-bottom:1px solid var(--line-1)}
.h .n{color:var(--signal)}
.traps{display:grid;grid-template-columns:1fr 1fr;gap:2.4mm}
.trap{background:var(--surface-card);border:1px solid var(--line-1);border-radius:3px;
padding:2.9mm 3.4mm}
.trap .chip{font-size:6.2pt;padding:1mm 1.8mm}
.trap p{font-size:7.8pt;line-height:1.45;color:var(--text-secondary);margin-top:1.6mm}
.trap p b{color:var(--text-primary);font-weight:500}
.steps{display:flex;gap:0;border:1px solid var(--line-1);border-radius:3px;overflow:hidden}
.st{flex:1;background:var(--surface-card);padding:2.4mm 2.6mm;border-left:1px solid var(--line-1)}
.st:first-child{border-left:0}
.st i{font-family:var(--font-mono);font-style:normal;font-size:6.4pt;color:var(--signal)}
.st div{font-size:8pt;font-weight:500;margin-top:0.9mm}
.st span{display:block;font-size:6.3pt;line-height:1.35;color:var(--text-tertiary);margin-top:0.7mm}
.tiers3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--line-1);
border:1px solid var(--line-1);border-radius:3px;overflow:hidden}
.tcell{background:var(--surface-card);padding:2.9mm 3.4mm}
.tcell .chip{font-size:6.2pt;padding:1mm 1.8mm}
.tcell p{font-size:7.6pt;line-height:1.45;color:var(--text-secondary);margin-top:1.6mm}
.duo{display:grid;grid-template-columns:1.15fr 1fr;gap:2.4mm}
/* the shared .panel is a run-report callout: mono caps in warn amber with an
   amber rule. On the sheet it is an ordinary panel, so put the display face
   back and drop the alarm colour. */
.panel{background:var(--surface-card);border:1px solid var(--line-1);
border-left:1px solid var(--line-1);border-radius:3px;padding:3.1mm 3.8mm;margin-bottom:0}
.panel h3{font-family:var(--font-display);font-size:10.5pt;font-weight:400;
letter-spacing:-0.01em;text-transform:none;color:var(--text-primary);margin-bottom:1.4mm}
.panel p{font-size:7.8pt;line-height:1.5;color:var(--text-secondary)}
.panel .mono{font-family:var(--font-mono);font-size:6.6pt;color:var(--text-tertiary);
letter-spacing:0.08em}
.ctafoot{margin-top:auto;background:var(--signal);color:var(--signal-ink);border-radius:3px;
padding:3.6mm 5mm;display:flex;justify-content:space-between;align-items:center;gap:6mm}
.ctafoot .big{font-family:var(--font-display);font-size:13pt;letter-spacing:-0.01em}
.ctafoot .mono{font-family:var(--font-mono);font-size:7pt;letter-spacing:0.08em;
text-align:right;line-height:1.7}

/* Screen only. The sheet is a fixed 210mm object, so on a phone it would push
   the document 794px wide and scroll sideways. Zooming it down keeps the whole
   page visible and leaves the print layout untouched: each band is chosen so
   794px times the zoom fits inside that band's narrowest viewport. */
@media screen and (max-width:820px){
html,body{width:auto;height:auto;overflow:visible}
body{display:flex;justify-content:center;align-items:flex-start;
background:var(--surface-page);padding:10px 0}
.sheet{zoom:0.87;flex:0 0 auto}}
@media screen and (max-width:700px){.sheet{zoom:0.70}}
@media screen and (max-width:560px){.sheet{zoom:0.54}}
@media screen and (max-width:430px){.sheet{zoom:0.45}}
@media screen and (max-width:360px){.sheet{zoom:0.34}}
"""

SHEET = """
<div class="sheet">
  <div class="mast">
    <span class="wordmark">Pramana&nbsp;<b>AI</b></span>
    <span class="tag">Evidence gated answers for security questionnaires</span>
  </div>

  <div>
    <h1>Every answer cited to an approved source, <i>or refused.</i></h1>
    <p class="lede">Pramana AI answers security questionnaires from your own approved evidence.
    Deterministic gates decide what ships, not model confidence: every released answer carries a
    citation, every refusal names its gap and routes to the right human, and nothing reaches the
    delivered workbook without a named reviewer in a tamper evident audit log.</p>
  </div>

  <div class="row3m">
    <div class="mcell"><b class="ok">0</b><span>Unsupported claims, enforced release rule</span></div>
    <div class="mcell"><b class="sig">~2 min</b><span>Ten gated answers, start to finish</span></div>
    <div class="mcell"><b class="ok">Public</b><span>Adversarial eval suite, on GitHub</span></div>
  </div>

  <div class="h"><span class="n">01</span><span>The four planted traps, refused correctly on every run</span></div>
  <div class="traps">
    <div class="trap"><span class="chip c-warn">CERT NEVER INFERRED</span>
      <p><b>Certification asked, roadmap on file.</b> The roadmap is retrieved, cited, then struck
      out: plans never qualify as certificates, however confident the draft sounds.</p></div>
    <div class="trap"><span class="chip c-warn">SOURCES CONFLICT</span>
      <p><b>Two approved policies disagree.</b> Both quarantined until an owner reconciles; questions citing either refuse too.</p></div>
    <div class="trap"><span class="chip c-warn">EVIDENCE EXPIRED</span>
      <p><b>Stale pentest report.</b> Cannot support a current claim; the refusal names the document, expiry, and owner.</p></div>
    <div class="trap"><span class="chip c-warn">ROUTED TO COUNSEL</span>
      <p><b>Unlimited liability demanded.</b> Legal commitments route before drafting; the model never sees them.</p></div>
  </div>

  <div class="h"><span class="n">02</span><span>How it works</span></div>
  <div class="steps">
    <div class="st"><i>01</i><div>Upload</div><span>Policies and reports. You attest approval.</span></div>
    <div class="st"><i>02</i><div>Retrieve</div><span>Your documents only. Tenants isolated.</span></div>
    <div class="st"><i>03</i><div>Draft</div><span>A model drafts. The gates never trust it.</span></div>
    <div class="st"><i>04</i><div>Gate</div><span>Cite or refuse. Stale, conflict, legal.</span></div>
    <div class="st"><i>05</i><div>Review</div><span>A named human releases, on the chain.</span></div>
  </div>

  <div class="h"><span class="n">03</span><span>Whose key drafts, and therefore whose terms apply</span></div>
  <div class="tiers3">
    <div class="tcell"><span class="chip c-sig">DEMO</span>
      <p><b>Our key, free.</b> Google Gemini free tier, whose terms let Google use submitted
      content to improve their services. Public evidence only. Three runs, deleted after 14 days.</p></div>
    <div class="tcell"><span class="chip c-ok">BYOK</span>
      <p><b>Your key, your terms.</b> Your text travels under your existing contract with your
      provider. This is the tier for confidential evidence.</p></div>
    <div class="tcell"><span class="chip c-rev">MANAGED</span>
      <p><b>Paid, with commitments.</b> A paid tier key carrying a no-training commitment, passed
      through to you in the contract rather than in a marketing line.</p></div>
  </div>

  <div class="duo">
    <div class="panel"><h3>What leaves your infrastructure</h3>
      <p>Documents stay in an isolated workspace and are deleted after 14 days. Retrieval runs on
      our server. The drafting model sees one question and its excerpts, never your full
      documents, never another tenant. Two sub-processors, named plainly: Google Gemini for
      drafting, Render for hosting. No analytics, anywhere.</p></div>
    <div class="panel"><h3>What you take away</h3>
      <p>Your workbook returned in its original structure, an audit working paper, and a hash
      chained log you can verify yourself.</p>
      <span class="mono">DELIVERED.xlsx / run_report.html / audit_log.jsonl</span></div>
  </div>

  <div class="ctafoot">
    <span class="big">Run it on our sample pack. No upload, no call, no form gate.</span>
    <span class="mono">github.com/dhruvshahi10/trustops<br>linkedin.com/in/dhruvshahi-<br>dhruv.shahi07@gmail.com</span>
  </div>
</div>
"""


def build() -> Path:
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Pramana AI one pager</title>"
        f"<style>{brand.stylesheet(PRINT_CSS)}</style></head>"
        f"<body>{SHEET}</body></html>"
    )
    dest = ROOT / "marketing" / "one-pager.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
    return dest


def build_pdf(src: Path) -> Path | None:
    """Print the sheet to A4. Returns None when Playwright is not installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    dest = ROOT / "marketing" / "Pramana-one-pager.pdf"
    # Playwright's default here is the headless shell, which this image does not
    # ship; the full Chromium it does ship is the one the capture scripts use.
    chrome = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    launch = {"executable_path": str(chrome)} if chrome.exists() else {}
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        page = browser.new_page()
        page.goto(src.as_uri())
        page.emulate_media(media="print")
        # PRINT_CSS already sets @page size and margin; print_background carries
        # the ink that print-color-adjust asks the browser to keep.
        page.pdf(path=str(dest), format="A4", print_background=True,
                 margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        browser.close()
    return dest


def main() -> None:
    dest = build()
    print(f"wrote {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024}KB)")
    pdf = build_pdf(dest)
    if pdf is None:
        print("skipped the PDF, playwright is not installed")
    else:
        print(f"wrote {pdf.relative_to(ROOT)} ({pdf.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
