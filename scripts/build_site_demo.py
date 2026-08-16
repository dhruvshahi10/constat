"""Build the landing page's interactive demo data from real engine output.

Runs the deterministic mock pipeline against the synthetic acme tenant and
writes site/demo/contracts.json: one contract per showcase question, exactly
what the live engine returns, so the landing demo is truthful without an API
call or a server. Rebuild whenever gates or evidence change:

    .venv/bin/python scripts/build_site_demo.py

It also assembles site/index.html from site/index.template.html, filling:

    /*@CSS@*/       the brand stylesheet with fonts inlined
    /*@DEMO@*/      the contracts, as JSON, for the client
    <!--@CHIPS@-->  the chip buttons
    <!--@Q0@-->     the first question
    <!--@VERDICT0@-->, <!--@ANSWER0@-->, <!--@PROV0@-->, <!--@GAPS0@-->

The last five exist so the demo frame is complete on first paint. Typing the
first question a character at a time meant the hero opened on roughly two
seconds of empty box, which is the worst possible first impression for a
product whose whole claim is that it shows its work.
"""
from __future__ import annotations

import html as _html
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trustops.drafter import make_drafter          # noqa: E402
from trustops.evidence import EvidenceStore        # noqa: E402
from trustops.gates import post_gate, pre_gate     # noqa: E402
from trustops.models import Draft, Question        # noqa: E402
from trustops.retrieve import Retriever            # noqa: E402

# (id, label shown on the chip, question, which trap it demonstrates)
#
# The ISO question is worded to actually retrieve the certification roadmap.
# The earlier phrasing retrieved nothing at all, so the card promised "CERT
# NEVER INFERRED" while the gap text underneath said "no approved evidence
# retrieved" — a plain retrieval miss dressed up as the flagship gate. A GRC
# buyer reads gap text closely, and that contradiction is exactly the kind of
# thing they are trained to catch. This wording makes the demonstration real:
# PLN-ISO-RM is retrieved, cited, and then struck out by the cert gate for
# being a roadmap.
SHOWCASE = [
    ("mfa", "MFA enforcement", "Is multi-factor authentication enforced for all workforce access to production systems?", "cited"),
    ("ir", "Incident response", "Do you have a documented incident response plan, and within what timeframe are customers notified of a confirmed breach?", "cited"),
    ("soc2", "SOC 2 attestation", "Do you hold a current SOC 2 Type II attestation?", "cited"),
    ("iso", "ISO 27001 trap", "Is your ISMS ISO 27001 certified? Provide the certificate number, certification body and expiry date.", "cert"),
    ("del", "Deletion contradiction", "Within how many days of contract termination is customer data deleted?", "contradiction"),
    ("pen", "Stale pentest", "Has an independent penetration test been performed in the last 12 months?", "stale"),
    ("legal", "Unlimited liability", "Will Vendor contractually commit to unlimited liability for any breach?", "legal"),
]

FIXED_TODAY = date(2026, 8, 16)


def verdict_for(d) -> tuple[str, str]:
    """Label a finished draft. Order matters: most specific gate wins.

    CERT_INFERENCE_BLOCKED and a bare CERT_CLAIM are different events and used
    to share a label. The first is the flagship trap: a certification claim was
    asked, real evidence came back, and the gate struck it out for being the
    wrong evidence class. The second is a certification question that simply
    found nothing, which is an ordinary retrieval miss. Calling both "CERT
    NEVER INFERRED" put a verdict on the card that the gap text underneath
    contradicted.
    """
    if d.route == "LEGAL":
        return "ROUTED TO COUNSEL", "legal"
    if d.abstained and any(f.startswith("CONTRADICTION") for f in d.gate_flags):
        return "REFUSED, SOURCES CONFLICT", "warn"
    if d.abstained and any(f.startswith("STALE_EVIDENCE") for f in d.gate_flags):
        return "REFUSED, EVIDENCE EXPIRED", "warn"
    if d.abstained and any(f.startswith("CERT_INFERENCE_BLOCKED") for f in d.gate_flags):
        return "REFUSED, CERT NEVER INFERRED", "warn"
    if d.abstained and any(f.startswith("UNGROUNDED_ANSWER") for f in d.gate_flags):
        return "REFUSED, NOT GROUNDED IN SOURCE", "warn"
    if d.abstained and any(f.startswith("CERT_CLAIM") for f in d.gate_flags):
        return "REFUSED, NO CERTIFICATE ON FILE", "warn"
    if d.abstained:
        return "REFUSED, GAP NAMED", "warn"
    if d.gaps or d.requires_human:
        # something citable survived, but a gate raised a finding on the way:
        # honest label, not "clean"
        return "CITED, HELD FOR HUMAN REVIEW", "rev"
    return "CITED, GATE CLEAN", "ok"


def answer(question_text: str, store: EvidenceStore, retriever: Retriever) -> dict:
    q = Question(question_id="DEMO", row=0, domain="Demo", text=question_text)
    d = Draft(question_id="DEMO", answer=None)
    d = pre_gate(q, d)
    if d.route != "LEGAL":
        d = make_drafter("mock", retriever).draft(q, "acme")
        d = pre_gate(q, d)
    d = post_gate(q, d, store, FIXED_TODAY)

    verdict, tone = verdict_for(d)
    return {
        "verdict": verdict, "tone": tone, "answer": d.answer,
        "citations": [f"{c.source_id} v{c.version} {c.location}" for c in d.citations],
        "gaps": d.gaps[:2], "flags": d.gate_flags[:2],
    }


CHIP_CLASS = {"ok": "chip c-ok", "legal": "chip c-sig", "rev": "chip c-rev"}

# --- legal pages -------------------------------------------------------------
# site/legal/*.html are built here rather than hand-maintained, for the same
# reason the landing page is: they use brand.stylesheet(), so they cannot drift
# from the product's palette, type or focus rules. Two placeholders are left
# deliberately visible for the founder to fill: [JURISDICTION] and, on the
# landing page, [CALENDAR_LINK].

LEGAL_CSS = """
body{padding-bottom:80px}
.legalwrap{max-width:760px}
.draftnote{background:var(--status-warn-wash);border:1px solid var(--line-1);
border-left:2px solid var(--status-warn);border-radius:var(--radius-2);padding:16px 18px;
margin:26px 0;font-size:13.5px;line-height:1.65;color:var(--text-primary)}
.draftnote b{color:var(--status-warn);font-weight:400;font-family:var(--font-mono);
font-size:10.5px;letter-spacing:0.13em;text-transform:uppercase;display:block;margin-bottom:7px}
.ph{font-family:var(--font-mono);font-size:0.92em;color:var(--status-warn);
background:var(--status-warn-wash);padding:1px 5px;border-radius:var(--radius-1)}
h2{margin-top:44px}
h3{font-size:18px;margin-top:26px;margin-bottom:6px}
.legalwrap p{font-size:14.5px;line-height:1.72;color:var(--text-secondary);margin-top:10px;
max-width:74ch}
.legalwrap li{font-size:14.5px;line-height:1.72;color:var(--text-secondary);margin-top:8px}
.legalwrap ul{margin:8px 0 0 20px}
.legalwrap strong{color:var(--text-primary);font-weight:500}
.tbl{margin-top:16px;overflow-x:auto}
.tbl table{min-width:520px}
.updated{font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.13em;
text-transform:uppercase;color:var(--text-tertiary);margin-top:14px}
.navback{margin-top:26px;font-family:var(--font-mono);font-size:11px}
"""

DRAFT_NOTE = """<div class="draftnote"><b>Founder drafted, pending legal review</b>
This document was written by the founder, not by a lawyer, and has not been through legal
review. It is published in this state deliberately: a pre-launch demo that collects documents
should say what it does with them from the first day rather than from the day it can afford
counsel. Where it is wrong it will be corrected, and material changes will be dated here.
If anything below matters to your decision, ask and you will get a straight answer in
writing.</div>"""


def _legal_page(title: str, heading: str, eyebrow: str, body: str) -> str:
    from trustops import brand
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title>"
        f"<style>{brand.stylesheet(LEGAL_CSS)}</style></head>"
        '<body><div class="wrap legalwrap">'
        f'<header><div class="eyebrow"><b>TrustOps</b> / {eyebrow}</div>'
        f"<h1>{heading}</h1>"
        '<div class="updated">Version 0.1 / 16 August 2026 / operator: TrustOps, '
        "operated by Dhruv Shahi</div></header>"
        f"{DRAFT_NOTE}{body}"
        '<p class="navback"><a href="/">Back to TrustOps</a> / '
        '<a href="/site/legal/terms.html">Terms</a> / '
        '<a href="/site/legal/privacy.html">Privacy and data handling</a></p>'
        "<footer>TrustOps, operated by Dhruv Shahi / "
        "governing law and venue: <span class=\"ph\">[JURISDICTION]</span> / "
        '<a href="mailto:dhruv.shahi07@gmail.com">dhruv.shahi07@gmail.com</a></footer>'
        "</div></body></html>")


TERMS_BODY = """
<h2>1. Who you are contracting with</h2>
<p>The service at this address is <strong>TrustOps, operated by Dhruv Shahi</strong>, an
individual operator. There is no company entity behind it yet. Governing law and the venue for
any dispute are <span class="ph">[JURISDICTION]</span>, to be completed by the operator before
any paid tier is sold. Until that placeholder is filled, treat the arrangement as governed by
the law of your own place of business for anything you would otherwise need certainty about,
and ask before you rely on this service for anything contractual.</p>

<h2>2. This is a demo, and it is sold as one</h2>
<p>TrustOps is pre-launch. It is provided <strong>as is and as available</strong>, with
<strong>no warranty</strong> of any kind, express or implied, including any warranty of
merchantability, fitness for a particular purpose, accuracy or non infringement. There is
<strong>no service level agreement</strong>, no uptime commitment, no support commitment and no
guarantee of continuity. The service may change, break or be withdrawn without notice, and a
workspace may be deleted early if the demo is being abused or if it costs more to run than the
operator can carry.</p>
<p>Nothing this service outputs is legal, audit or compliance advice. Every answer it drafts is
a draft. The whole design of the product is that a named human reviews before anything is
released, and that design assumes you actually do the reviewing. If you send a TrustOps answer
to a customer without reading it, that is your representation to your customer, not ours.</p>

<h2>3. What you may upload</h2>
<p>On the free demo tier, drafting runs on <strong>Google Gemini's free tier</strong>, whose
terms permit Google to use submitted content to improve their services. So the rule for this
tier is simple and you agree to it by uploading:</p>
<ul>
<li><strong>Upload public evidence only.</strong> A published SOC 2 report, an ISO certificate,
trust-center policies, anything you would be comfortable seeing outside your company.</li>
<li><strong>Do not upload confidential, personal or regulated data.</strong> No customer data,
no personal data of third parties, no secrets, no material non-public information.</li>
<li>Do not upload anything you do not have the right to upload.</li>
<li>Do not use the service to break the law, to attack it or anyone else, or to generate
misleading claims about your security posture.</li>
</ul>
<p>If you need to run TrustOps over confidential evidence, that is the BYOK tier, where you
supply your own provider key and your text travels under your contract with that provider. Ask
for it. It is not built yet, and saying so is more useful to you than a checkbox that pretends
otherwise.</p>

<h2>4. Your material stays yours</h2>
<p>You keep all right, title and interest in the documents you upload and in the answers
produced from them. <strong>We claim no ownership of your intellectual property and no licence
to it beyond what is technically required to run the service you asked for</strong>: storing the
document in your workspace, indexing it so it can be retrieved, sending a question and the
retrieved excerpts to the drafting model, and generating your report and workbook. We do not
sell, licence or share your documents. We do not use them to train anything of ours; note that
this is a statement about us and not about Google, whose free-tier terms are described above and
on the <a href="/site/legal/privacy.html">privacy page</a>.</p>

<h2>5. Limits on the free tier</h2>
<ul>
<li>Three runs per workspace.</li>
<li>Twenty documents per workspace, five megabytes per file.</li>
<li>Three signups per network per day.</li>
<li>The workspace and everything in it is hard deleted fourteen days after signup.</li>
</ul>
<p>Your workspace link is the only credential. There is no password and no reset. If you lose
the link you lose the workspace, and we cannot recover it for you, because the link is the
capability and we store only a hash of it.</p>

<h2>6. Liability</h2>
<p>To the maximum extent the law allows, the operator is not liable for indirect, incidental,
special, consequential or punitive damages, or for lost profits, lost revenue, lost data or
business interruption, arising from your use of this demo. Total aggregate liability for any
claim relating to the free tier is limited to the amount you paid for it, which is nothing.
Some jurisdictions do not allow these exclusions, in which case they apply only as far as that
jurisdiction permits.</p>

<h2>7. Ending it</h2>
<p>You can stop using the service at any time, and you can ask for your workspace to be deleted
immediately rather than waiting for the fourteen day sweep. The operator may suspend or delete a
workspace that breaks section 3, that threatens the service, or that makes the demo
unaffordable to run.</p>

<h2>8. Changes and contact</h2>
<p>These terms will change, because the product is early. Material changes will be dated at the
top of this page. Questions, corrections and deletion requests go to
<a href="mailto:dhruv.shahi07@gmail.com">dhruv.shahi07@gmail.com</a> and are answered by a
person.</p>
"""

PRIVACY_BODY = """
<p>Short version, because the long version below only exists so this one is checkable: we
collect your organization name, an email address, your IP address and whatever text is in the
documents you upload. We keep uploads for fourteen days and then hard delete them. Two
sub-processors, Google and Render, and no others. One cookie, which logs you in and does
nothing else. No analytics, no trackers, no advertising pixels, on any page of this site.</p>

<h2 id="data-handling">Data handling</h2>

<h3>What we collect, and why</h3>
<div class="tbl"><table>
<tr><th>What</th><th>Why</th><th>How long</th></tr>
<tr><td><strong>Organization name</strong></td><td>Names your workspace and titles the
generated questionnaire and report.</td><td>Kept after workspace deletion, in the signup
record.</td></tr>
<tr><td><strong>Email address</strong></td><td>Identifies the signup, lets us contact you about
the demo, and is offered as the default document owner on the upload form. We do not send the
workspace link by email and we do not run a mailing list.</td><td>Kept after workspace deletion,
in the signup record.</td></tr>
<tr><td><strong>IP address</strong></td><td>Rate limiting only. Three signups per network per
day is the only thing standing between this demo and an unpaid API bill.</td><td>Deleted after
seven days.</td></tr>
<tr><td><strong>Uploaded documents and their extracted text</strong></td><td>Retrieval and
drafting. This is the product.</td><td><strong>Hard deleted fourteen days after
signup</strong>, with the whole workspace directory.</td></tr>
<tr><td><strong>Run outputs</strong> (report, workbook, audit log)</td><td>The deliverables you
came for.</td><td>Deleted with the workspace at fourteen days; older run directories are pruned
sooner, keeping the newest five.</td></tr>
<tr><td><strong>Reviewer name and note</strong></td><td>Named review is the point of the audit
chain. You type the name yourself; in the demo it is self attested and unverified.</td>
<td>Stored in the approvals record, which is not swept with the workspace.</td></tr>
<tr><td><strong>Run metadata</strong> (identifiers, timings, counts, error text)</td>
<td>Operating the queue and debugging failures.</td><td>Retained.</td></tr>
<tr><td><strong>Server logs</strong></td><td>Written to the host's log stream for operations.
They contain request lines and client addresses.</td><td>Held by the host under its own
retention.</td></tr>
</table></div>
<p>We do not ask for and do not want special category personal data, payment details or
credentials. If you upload them by mistake, email us and we will delete the workspace
immediately rather than waiting for the sweep.</p>

<h3>The free tier reality, in one sentence</h3>
<p><strong>Drafting on this demo runs on Google Gemini's free tier, whose terms allow Google to
use submitted content to improve their services, which is why this tier asks you to upload
public evidence only and why we make no no-training claim on your behalf.</strong></p>
<p>We used to write "never used for training" on the landing page. It was true of us and
misleading about the stack, so it is gone. What is accurate: <em>we</em> do not train on your
documents, and on this tier we cannot make that promise for the model provider. The BYOK tier
exists so that promise comes from the provider you already have a contract with, and the Managed
tier exists so it comes from a paid tier that carries it in writing.</p>

<h3>Sub-processors</h3>
<div class="tbl"><table>
<tr><th>Who</th><th>What they do</th><th>What they receive</th></tr>
<tr><td><strong>Google</strong> (Gemini API)</td><td>Drafts each answer.</td><td>One question
and the excerpts retrieved for it, per answer. Never your full documents, never your document
list, never another tenant's material.</td></tr>
<tr><td><strong>Render</strong></td><td>Hosts the server and the disk your workspace sits
on.</td><td>Everything stored, as any host does, plus request logs.</td></tr>
</table></div>
<p><strong>There are no other sub-processors.</strong> No analytics vendor, no error tracking
vendor, no CDN, no email service provider, no third party retrieval or indexing service. If that
list ever grows, it grows on this page first.</p>

<h3>Where processing happens</h3>
<p>Retrieval, indexing, the gates, the audit chain and every generated file are produced on our
own server. The only outbound call in a run is the drafting call to Google. Tenants are
structurally isolated: each workspace has its own directory and its own index, and the retrieval
layer is rooted inside it rather than filtered after the fact.</p>

<h3>Cookies</h3>
<p>One cookie, <span class="ph">tt_&lt;workspace&gt;</span>, set the first time you open your
workspace link. It is strictly necessary: it is what keeps you signed in to that workspace. It
is HttpOnly, SameSite=Lax, Secure, scoped to your workspace path, and expires after fourteen
days. <strong>There are no analytics cookies, no advertising cookies and no third party scripts
of any kind on this site</strong>, which is why you were never shown a cookie banner. That is a
deliberate product decision and a difference worth noticing when you compare this to the other
tools in this category.</p>

<h3>Your rights</h3>
<p>Whatever framework applies to you, the practical answer is the same and does not require a
form:</p>
<ul>
<li><strong>Access</strong>: ask and we will tell you exactly what is stored against your
workspace.</li>
<li><strong>Deletion</strong>: ask and the workspace and all its files are deleted immediately.
Otherwise it happens automatically at fourteen days.</li>
<li><strong>Correction</strong>: ask, or just re-upload.</li>
<li><strong>Objection and portability</strong>: your documents are your documents; everything
the run produced is downloadable from your workspace while it exists.</li>
<li><strong>Complaint</strong>: you may complain to the supervisory authority in
<span class="ph">[JURISDICTION]</span> once the operator has completed that placeholder.</li>
</ul>
<p>Requests go to <a href="mailto:dhruv.shahi07@gmail.com">dhruv.shahi07@gmail.com</a>. They are
read by one person, which in practice means a same week answer, not a ticket number.</p>

<h3>Children</h3>
<p>This is a business tool and is not directed at anyone under 16.</p>

<h3>Security, honestly</h3>
<p>Your workspace link is a bearer capability: anyone holding it holds the workspace. We store
only a hash of it. There is no password, no multi-factor authentication and no session
management beyond that cookie, because this is a demo. Treat the link like a password, and do
not put evidence in this tier that would hurt you if the link leaked.</p>
"""


def build_legal(root: Path) -> list[Path]:
    out_dir = root / "site" / "legal"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, title, heading, eyebrow, body in (
        ("terms.html", "TrustOps terms of use", "Terms of use", "legal / terms", TERMS_BODY),
        ("privacy.html", "TrustOps privacy and data handling",
         "Privacy and data handling", "legal / privacy", PRIVACY_BODY),
    ):
        p = out_dir / name
        p.write_text(_legal_page(title, heading, eyebrow, body), encoding="utf-8")
        written.append(p)
    return written


def prerender(first: dict) -> dict[str, str]:
    """Server-side render of the first contract, so the frame has content
    before a single line of demo JS runs."""
    e = _html.escape
    prov = (f'<div class="d-prov">{"<br>".join(e(c) for c in first["citations"])}</div>'
            if first["citations"] else '<div class="d-prov warn">no citation released</div>')
    gaps = "".join(f'<div class="d-gap">&#9656; {e(g)}</div>' for g in first["gaps"])
    answer_html = (f'{e(first["answer"])}' if first["answer"]
                   else "<em>No answer released.</em>")
    chip = CHIP_CLASS.get(first["tone"], "chip c-warn")
    return {
        "Q0": e(first["question"]),
        "VERDICT0": f'<span class="{chip}" id="verdict">{e(first["verdict"])}</span>',
        "ANSWER0": answer_html,
        "PROV0": prov,
        "GAPS0": gaps,
    }


def chips_html(out: dict) -> str:
    e = _html.escape
    return "".join(
        f'<button type="button" data-k="{e(k)}" aria-pressed="false">{e(v["label"])}</button>'
        for k, v in out.items())


def main() -> None:
    store = EvidenceStore("acme", ROOT / "data" / "evidence")
    retriever = Retriever(store)
    out = {}
    for key, label, text, trap in SHOWCASE:
        out[key] = {"label": label, "question": text, "trap": trap,
                    **answer(text, store, retriever)}
    dest = ROOT / "site" / "demo" / "contracts.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    refused = sum(1 for v in out.values() if v["tone"] != "ok")
    print(f"wrote {dest}: {len(out)} contracts, {refused} refusals")

    # the flagship card is only honest if the cert gate actually fired
    iso_flags = out["iso"]["flags"]
    if not any(f.startswith("CERT_INFERENCE_BLOCKED") for f in iso_flags):
        print(f"  WARNING: the ISO showcase no longer triggers the cert gate "
              f"(flags={iso_flags}). The landing card claims it does.")
    for key, v in out.items():
        print(f"  {key:6} {v['verdict']}")

    # assemble the final landing page: brand CSS + fonts + demo data inlined,
    # so the page is one self-contained file with zero external requests
    from trustops import brand
    template = (ROOT / "site" / "index.template.html").read_text(encoding="utf-8")
    page = template.replace("/*@CSS@*/", brand.stylesheet())
    page = page.replace("/*@DEMO@*/", json.dumps(out, ensure_ascii=False))
    page = page.replace("<!--@CHIPS@-->", chips_html(out))
    first_key = next(iter(out))
    for name, html in prerender(out[first_key]).items():
        page = page.replace(f"<!--@{name}@-->", html)
    leftovers = [m for m in ("@CSS@", "@DEMO@", "@CHIPS@", "@Q0@", "@VERDICT0@",
                             "@ANSWER0@", "@PROV0@", "@GAPS0@") if m in page]
    if leftovers:
        raise SystemExit(f"unfilled template placeholders: {leftovers}")
    (ROOT / "site" / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote site/index.html ({len(page) // 1024}KB)")

    for p in build_legal(ROOT):
        print(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
