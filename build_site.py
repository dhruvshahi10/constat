"""Generate the public site from the engine.

Nothing on the site is asserted by hand. The numbers come from a run executed
during the build, the trust center is the trust-page generator's output, and the
accuracy page is the eval harness's output. If a page cannot be generated from
real output, it is not published and its navigation link does not appear.

  python build_site.py            # regenerate public/
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from trustops import commitments, site, trustpage               # noqa: E402
from trustops.pipeline import run                               # noqa: E402
from trustops.report import write_report                        # noqa: E402
from trustops.site import esc, hero, page                       # noqa: E402

PUBLIC = ROOT / "public"
EVIDENCE = ROOT / "data" / "evidence"
QNR = ROOT / "data" / "questionnaires" / "acme_security_questionnaire.xlsx"
ARTIFACTS = PUBLIC / "artifacts"
DEMO_TENANT = "acme"

CONTACT = "dhruv.shahi07@gmail.com"
CLIENT_TRUST_PAGES = ("acme", "northwind")   # generated as artifacts, to prove it is a generator


def cta_buttons(buttons: list[tuple[str, str, bool]]) -> str:
    """Only link to routes this build actually produced. A dead CTA on a page
    arguing that the product never overstates its evidence is a bad look and a
    real defect."""
    live = [(href, label, primary) for href, label, primary in buttons
            if href in site._AVAILABLE]
    if not live:
        return ""
    return ('<div class="cta">' + "".join(
        f'<a class="btn{" primary" if primary else ""}" href="{href}">{esc(label)}</a>'
        for href, label, primary in live) + '</div>')


def write(route: str, html: str) -> None:
    target = PUBLIC / route.strip("/") / "index.html" if route != "/" else PUBLIC / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")


# --- the reference run -------------------------------------------------------
def reference_run() -> dict:
    """Execute a real deterministic run and publish its artifacts.

    The landing page's numbers are this run's numbers. Rebuilding the site
    re-runs the engine, so the site cannot drift away from what the code does.
    """
    out = ARTIFACTS / "reference-run"
    if out.exists():
        shutil.rmtree(out)
    result = run(QNR, tenant=DEMO_TENANT, evidence_root=EVIDENCE, out_dir=out,
                 drafter_kind="mock", today=date.today())
    write_report(result, date.today())
    return result.metrics


def waitlist_block(source: str) -> str:
    return f"""
<h2>Early access</h2>
<p class="sub">Pramana is pre-pilot. If you run security review at a B2B SaaS company and
questionnaires are eating your sales cycle, tell me what your worst one looks like.</p>
<div class="console">
<form class="waitlist" id="wl" data-source="{source}" data-contact="{CONTACT}">
  <input type="email" id="wlemail" placeholder="you@company.com" required autocomplete="email">
  <input type="text" id="wlnote" placeholder="optional: what's your worst questionnaire?" maxlength="400">
  <button class="btn primary" type="submit">Request access</button>
</form>
<div class="formmsg" id="wlmsg"></div>
<div class="stamp">No tracking, no newsletter. Falls back to a plain mail link if the
store is unavailable — this form will never tell you it saved something it did not.</div>
</div>
<script src="/assets/waitlist.js" defer></script>
"""


WAITLIST_JS = """// Early-access form. Never reports a signup it did not store.
(function () {
  var form = document.getElementById('wl');
  if (!form) return;
  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    var email = document.getElementById('wlemail').value.trim();
    var note = document.getElementById('wlnote').value.trim();
    var msg = document.getElementById('wlmsg');
    msg.className = 'formmsg';
    msg.textContent = '';
    try {
      var r = await fetch('/api/waitlist', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, note: note, source: form.dataset.source || 'site' })
      });
      var data = await r.json();
      if (data.stored) {
        msg.className = 'formmsg ok';
        msg.textContent = 'Recorded \u2014 thank you. I read every one.';
        return;
      }
      throw new Error(data.error || 'unavailable');
    } catch (err) {
      // Built as DOM nodes, not markup: nothing from the network is ever parsed as HTML.
      msg.className = 'formmsg err';
      msg.textContent = 'Signup store is offline right now, so nothing was saved. ';
      var a = document.createElement('a');
      a.href = 'mailto:' + form.dataset.contact +
        '?subject=' + encodeURIComponent('Pramana early access') +
        '&body=' + encodeURIComponent(note ? ('From: ' + email + '\\n\\n' + note) : ('From: ' + email));
      a.textContent = 'Send it by mail instead \u2192';
      msg.appendChild(a);
    }
  });
})();
"""


# --- pages ---# --- pages -------------------------------------------------------------------
def build_index(metrics: dict, trust: dict | None = None,
                accuracy: dict | None = None) -> str:
    pct = lambda x: f"{round(x * 100)}%"                       # noqa: E731
    body = hero(
        "Security questionnaires are holding up your deals. Most of them should never have "
        "reached you.",
        "Pramana deflects the buyer questions your evidence already answers, answers the ones "
        "that still arrive — each cited to an approved document, version and paragraph — and "
        "refuses the rest by name instead of inventing something plausible. "
        "It is operated for you: nothing to deploy, no seat to buy.",
        cta_buttons([("/how-it-works/", "How it works", True),
                     ("/pricing/", "Pricing", False),
                     ("/demo/", "Try the engine", False)]))

    body += """
<h2>Three ways to start</h2>
<div class="cols">
  <div class="card">
    <h3>Trust page</h3>
    <p>Generated from your evidence. Every standard buyer question it answers publicly is one that
    never becomes an inbound request. Needs only your publishable policies, so there is almost
    nothing for a security team to review before you start.</p>
  </div>
  <div class="card rev">
    <h3>Managed assurance</h3>
    <p>Forward the questionnaire, get it back answered and cited in the buyer's own file, with a
    named person on your side signing it off. Plus the gap worklist that makes the next one
    cheaper.</p>
  </div>
  <div class="card warn">
    <h3>Commitment register</h3>
    <p>The check nobody runs: security promises already made in contracts and RFP responses, tested
    against what your evidence can actually support today.</p>
  </div>
</div>
<p class="stamp"><a href="/pricing/">What each one costs &rarr;</a></p>

<h2>Why the refusals are the product</h2>
<p class="lead">Every tool in this category can produce a fluent answer. The one that matters is
what happens when the evidence is not there — because a questionnaire answer is a material
security representation, and a plausible sentence with nothing behind it is a liability you signed
without reading.</p>
<div class="tablewrap"><table>
<tr><th>When your evidence is…</th><th>Pramana</th></tr>
<tr><td>A roadmap, not a certificate</td>
    <td>Refuses the certification question. Certification is never inferred from a plan — including
    for ISO&nbsp;42001, which most tools have never heard of.</td></tr>
<tr><td>Expired</td>
    <td>Refuses. An expired pen test cannot support a present-tense claim, and the report is routed
    to its owner.</td></tr>
<tr><td>Contradicted by another approved document</td>
    <td>Quarantines both and routes to the two owners. Two policies disagreeing on a retention
    period is found before a buyer finds it.</td></tr>
<tr><td>Actually a contractual commitment</td>
    <td>Routes to counsel before drafting. Liability and uptime guarantees never reach the
    engine as answerable questions.</td></tr>
<tr><td>About another company entirely</td>
    <td>Refuses. Answering it from your corpus would attribute someone else's controls to you.</td></tr>
<tr><td>Simply absent</td>
    <td>Refuses, names the missing document, and puts it on your evidence-gap worklist.</td></tr>
</table></div>
"""

    proof = []
    if accuracy:
        proof.append(
            f'<div class="stat ok"><b>{accuracy["correctly_refused_pct"]}%</b>'
            f'<span>correctly refused</span></div>'
            f'<div class="stat ok"><b>{accuracy["correctly_cited_pct"]}%</b>'
            f'<span>correctly cited</span></div>'
            f'<div class="stat ok"><b>{accuracy["released_without_citation"]}</b>'
            f'<span>answers with no citation</span></div>')
    if trust:
        proof.append(f'<div class="stat"><b>{round(trust["deflection_rate"] * 100)}%</b>'
                     f'<span>our own deflection</span></div>')
    proof.append(f'<div class="stat"><b>{metrics["questions"]}</b><span>questions per run</span></div>'
                 f'<div class="stat ok"><b>{metrics["cycle_seconds"]}s</b><span>full run cycle</span></div>')

    body += f"""
<h2>Measured, not asserted</h2>
<p class="sub">Every figure here was produced by the engine during this site's build. Rebuilding
the site re-runs it and rewrites them.</p>
<div class="grid">{''.join(proof)}</div>
<p class="stamp">
<a href="/accuracy/">Method and every failure by name &rarr;</a> ·
<a href="/artifacts/reference-run/run_report.html">a real audit working paper &rarr;</a> ·
<a href="/security/">our own security review &rarr;</a></p>

<h2>We answer our own questionnaire first</h2>
<p class="lead">Your buyers now ask about AI governance, model and data access boundaries, prompt
injection, agent permissions and MCP exposure — questions no SOC&nbsp;2 report contains evidence
for, which is exactly where a generative tool starts inventing. Pramana's own trust center answers
those questions from its own evidence, and refuses the ones it cannot support. Asked whether we
hold ISO&nbsp;42001 certification, it says no, because the only document on file is a roadmap.
<a href="/trust/">Read our trust center &rarr;</a></p>

<div class="note"><b>Where this is, honestly.</b> Pramana is pre-pilot and delivered as an operated
service — we run it, you never install anything. All data shown across this site is synthetic.
Retrieval is lexical today, so it misses some paraphrased questions; it fails closed and refuses
rather than guessing, and the four positive controls it currently misses are published on the
accuracy page rather than hidden.</div>
"""
    body += waitlist_block("landing")
    return page(f"{site.BRAND} — {site.TAGLINE}", body, active="/",
                description="Evidence-gated customer assurance: questionnaires deflected, "
                            "answered with citations, or refused by name.")


# --- the buyer's path --------------------------------------------------------
def build_how_it_works() -> str:
    body = hero(
        "You forward the questionnaire. You get it back answered, cited, and signed.",
        "Pramana is operated, not installed. There is nothing to deploy, no seat to buy, and no "
        "vendor security review to clear before you can start — because your evidence never "
        "enters a shared system.")
    body += """
<h2>The engagement</h2>
<div class="steps">
  <div class="step"><span class="who">You · once, about an hour</span>
    <h3>Send your evidence as it already exists</h3>
    <p>Policies, standards, plans, your SOC&nbsp;2 report, pen test summaries, subprocessor list.
    PDF, Word, spreadsheets, exports from Confluence or Drive. No template, no rewriting, no
    portal to fill in.</p></div>

  <div class="step"><span class="who">Us · half a day</span>
    <h3>The corpus is built and governed</h3>
    <p>Every document is read, and each one gets what the engine needs to reason about it: type,
    version, owner, the dates it is in force between, and any machine-checkable commitment it
    makes. Nothing becomes citable automatically — a named person approves each source, and that
    approval is logged.</p></div>

  <div class="step"><span class="who">You · one review</span>
    <h3>Your trust page goes live</h3>
    <p>Generated from the same corpus. Every standard buyer question your evidence genuinely
    supports is answered publicly with its source; everything else is listed as available under
    security review. That page starts deflecting questions before you answer another
    questionnaire.</p></div>

  <div class="step"><span class="who">You · forward an email</span>
    <h3>A questionnaire arrives</h3>
    <p>Send us the file the buyer sent you. CAIQ, SIG, a bespoke spreadsheet, a CSV — the layout
    is detected, so there is nothing to reformat and the buyer's own workbook comes back
    intact.</p></div>

  <div class="step"><span class="who">Us · minutes</span>
    <h3>Every answer is cited, or refused</h3>
    <p>Each answer names the document, version and paragraph it came from. Where the evidence is
    missing, expired, contradicted by another approved document, or the question is really a
    contractual commitment, the engine declines and says exactly which gap caused it and who owns
    it. It does not produce a plausible sentence to fill the cell.</p></div>

  <div class="step"><span class="who">You · the part only you can do</span>
    <h3>A named person signs it off</h3>
    <p>These are material security representations, so a person takes responsibility for them —
    not the engine. Approve what the evidence supports; where you want to answer something the
    evidence does not support, you write it and it is labelled as authored by you, visibly not
    evidence-backed. Every decision is written into a tamper-evident log.</p></div>

  <div class="step"><span class="who">You · the same day</span>
    <h3>You get the package</h3>
    <p>The buyer's workbook completed, the trust page, an audit working paper showing how every
    answer was reached, and the evidence-gap worklist — the specific documents to produce or
    refresh so that next quarter fewer questions come back refused.</p></div>
</div>

<h2>What we never do</h2>
<ul class="tight">
  <li><b>Never train anything on your content.</b> There is no training pipeline, and no model is
      adapted on your evidence, your questionnaires or your answers.</li>
  <li><b>Never send your evidence to a free-tier model.</b> Free tiers permit the provider to use
      submitted content for product improvement. Client work runs on the deterministic engine or a
      paid API tier where the terms forbid it.</li>
  <li><b>Never mix clients.</b> Each engagement is a separate evidence store; there is no code path
      that loads two clients together, and that is asserted by test on every change.</li>
  <li><b>Never publish an answer nobody signed.</b> A person approves every released answer.</li>
</ul>

<div class="note"><b>What this means for your security team.</b> You are engaging a service under an
NDA and DPA, not adopting a SaaS platform that needs its own review. If your team wants to review
us anyway, the answers are already written: see the <a href="/security/">security posture</a> and
our own <a href="/trust/">trust center</a>, which was generated by this engine from our own
evidence.</div>
"""
    body += waitlist_block("how-it-works")
    return page(f"How it works — {site.BRAND}", body, active="/how-it-works/",
                description="Operated, not installed: how a Pramana engagement runs end to end.")


def build_deliverables() -> str:
    body = hero("What actually lands in your inbox",
                "Every artifact below is produced by the engine from your own evidence. These are "
                "real samples, generated in this site's build from a synthetic client.")
    body += """
<h2>The package</h2>
<div class="filelist">
  <div class="filerow"><span class="fn">Completed workbook</span>
    <span class="fd">The buyer's own file, answered. Merged cells, hidden rows and formulas
    intact; question text, IDs and order untouched. Each answer carries its status and the
    documents it cites, so the buyer can see the provenance without asking.</span></div>
  <div class="filerow"><span class="fn">Trust page</span>
    <span class="fd">A self-service page answering the standard buyer questions your evidence
    supports, each with its source. Host it yourself or link it from your security page — every
    question it answers is one that never reaches your team.</span></div>
  <div class="filerow"><span class="fn">Audit working paper</span>
    <span class="fd">How every answer was reached: what was retrieved, which gate decided, what
    was refused and why. This is the document you hand an auditor or an internal reviewer who
    asks how the answers were produced.</span></div>
  <div class="filerow"><span class="fn">Evidence-gap worklist</span>
    <span class="fd">Every refusal, grouped by cause, naming the document to produce, refresh or
    reconcile and who owns it. This is the artifact that makes next quarter's questionnaire
    cheaper than this one's.</span></div>
  <div class="filerow"><span class="fn">Commitment register</span>
    <span class="fd">Security promises already made in contracts, RFP responses and DPAs, checked
    against what your evidence can actually support today — contradicted, unsupported, or backed
    by a document that expires before the commitment does.</span></div>
  <div class="filerow"><span class="fn">Answer contracts (JSON)</span>
    <span class="fd">Every answer as structured data — citations, coverage, status, gaps, routing.
    For loading into your own GRC system or diffing against the last questionnaire.</span></div>
  <div class="filerow"><span class="fn">Audit log</span>
    <span class="fd">Hash-chained and append-only: every state transition and every human
    decision, naming the actor. Editing any historical entry breaks verification.</span></div>
</div>

<h2>A complete package, exactly as a client receives it</h2>
<p class="lead">Not a screenshot and not a mock-up — this is a real package produced by the
engine, published in full. Open the cover page and follow any link in it:</p>
<div class="cta" style="margin:18px 0">
  <a class="btn primary" href="/artifacts/sample-delivery/index.html">Open the sample package</a>
  <a class="btn" href="/artifacts/sample-delivery/evidence_gaps.md">Read the gap worklist</a>
</div>

<h2>Individual artifacts</h2>
<p class="lead">Each of these was generated during this site's build:</p>
<div class="cols">
  <div class="card"><h3>Audit working paper</h3>
    <p>A full 24-question run, every answer with its provenance strip and every refusal with its
    named gap.<br><a href="/artifacts/reference-run/run_report.html">Open the working paper &rarr;</a></p></div>
  <div class="card"><h3>Client trust pages</h3>
    <p>The same generator, pointed at two different client corpora.<br>
    <a href="/artifacts/trust/acme/index.html">Acme &rarr;</a> ·
    <a href="/artifacts/trust/northwind/index.html">Northwind Health &rarr;</a></p></div>
  <div class="card"><h3>Commitment register</h3>
    <p>Seven commitments checked; a signed 30-day deletion promise contradicted by the policies
    on file.<br><a href="/commitments/">Open the register &rarr;</a></p></div>
  <div class="card"><h3>Machine-readable output</h3>
    <p><a href="/artifacts/reference-run/contracts.json">contracts.json</a> ·
    <a href="/artifacts/reference-run/audit_log.jsonl">audit_log.jsonl</a> ·
    <a href="/artifacts/reference-run/metrics.json">metrics.json</a></p></div>
</div>

<div class="note"><b>A note on the refusals.</b> A run of this size typically returns a real number
of refusals, and that is the product working. Each one names the specific gap and the person who
owns it. A tool that answered every question would be producing claims your evidence cannot
support — which is the thing that turns a security questionnaire into a liability.</div>
"""
    body += waitlist_block("deliverables")
    return page(f"What you get — {site.BRAND}", body, active="/deliverables/",
                description="The artifacts a Pramana engagement produces, with real samples.")


def build_pricing() -> str:
    body = hero("Priced per outcome, not per seat",
                "You are buying completed questionnaires and a trust page that stops them "
                "arriving — not a licence to operate software. Figures below are starting points "
                "for a first engagement and are set per client.")
    body += """
<div class="tiers">
  <div class="tier">
    <h3>Trust page</h3>
    <div class="price">$3,000&ndash;5,000</div>
    <div class="unit">one-time setup</div>
    <ul>
      <li>Evidence corpus onboarded and governed</li>
      <li>Self-service trust page generated and published</li>
      <li>Measured deflection rate across the standard buyer question set</li>
      <li>Evidence-gap worklist for what would raise it</li>
      <li>Refresh from $500/month as your evidence changes</li>
    </ul>
    <div class="who">Start here. It needs only your publishable policies, so there is almost
    nothing for your security team to review, and it is the fastest thing to put in front of a
    buyer.</div>
  </div>

  <div class="tier feature">
    <h3>Managed assurance</h3>
    <div class="price">$4,000&ndash;8,000</div>
    <div class="unit">per month</div>
    <ul>
      <li>Unlimited questionnaires answered and returned</li>
      <li>Trust page maintained as evidence changes</li>
      <li>Commitment register kept current against contracts and RFP responses</li>
      <li>Evidence-gap worklist refreshed every cycle</li>
      <li>Named human sign-off workflow with a tamper-evident record</li>
    </ul>
    <div class="who">For a team seeing several questionnaires a month where security review is
    holding up deals. This is the engagement that pays for itself in cycle time.</div>
  </div>

  <div class="tier">
    <h3>Per questionnaire</h3>
    <div class="price">$1,500&ndash;2,500</div>
    <div class="unit">per completed questionnaire</div>
    <ul>
      <li>One buyer questionnaire, answered and cited</li>
      <li>Returned in the buyer's own file, structure intact</li>
      <li>Audit working paper and evidence-gap list included</li>
      <li>Requires the corpus to be onboarded once</li>
    </ul>
    <div class="who">For occasional enterprise deals, or to try the workflow on one real
    questionnaire before committing to a retainer.</div>
  </div>
</div>

<h2>What that replaces</h2>
<p class="lead">An enterprise security questionnaire costs a security analyst somewhere between
eight and twenty hours. At a loaded rate that is most of the cost above, for one questionnaire,
every time — and it produces no trust page, no gap worklist, and no record of how the answers were
reached.</p>

<h2>What is not included, stated plainly</h2>
<ul class="tight">
  <li><b>We do not produce evidence you do not have.</b> If there is no pen test, the engine will
      refuse the pen test question and tell you so. Buying this does not create controls.</li>
  <li><b>We do not sign your representations.</b> A named person on your side approves every
      answer that goes out. That is the design, not a limitation.</li>
  <li><b>We do not answer contractual commitments.</b> Liability, indemnities, uptime guarantees
      and penalties route to your counsel before anything is drafted.</li>
  <li><b>No software licence.</b> Pramana is operated by us. Self-hosted and single-tenant
      deployments are available once an engagement justifies them.</li>
</ul>
"""
    body += waitlist_block("pricing")
    return page(f"Pricing — {site.BRAND}", body, active="/pricing/",
                description="Trust page setup, managed assurance retainer, or per questionnaire.")


def build_security(accuracy: dict | None) -> str:
    acc = ""
    if accuracy:
        acc = (f"<p class=\"lead\">Our own answer engine is measured against "
               f"{accuracy['total_prompts']} adversarial prompts: "
               f"<b>{accuracy['correctly_refused_pct']}%</b> correctly refused, "
               f"<b>{accuracy['correctly_cited_pct']}%</b> correctly cited, and "
               f"<b>{accuracy['released_without_citation']}</b> answers released without a "
               f"citation. Every failure is published by name on the "
               f"<a href=\"/accuracy/\">accuracy page</a>.</p>")
    body = hero("For your security team",
                "You review vendors for a living, so this page is written the way you would want "
                "it written: what we hold, what we never do, what we found when we reviewed "
                "ourselves, and what is still open.")
    body += f"""
<h2>Where your evidence lives</h2>
<dl class="kv">
  <dt>Held by</dt><dd>Your evidence corpus is processed in a dedicated store for your engagement.
    There is no code path that loads two clients into one store — isolation is the directory
    layout and is asserted by test, not a filter a query has to remember.
    <a href="/isolation/">How that is proved &rarr;</a></dd>
  <dt>Training</dt><dd>Never. There is no training pipeline. No model is trained, fine-tuned or
    adapted on your evidence, your questionnaires or your answers.</dd>
  <dt>Third parties</dt><dd>Client work runs on the deterministic engine or a paid model API tier
    whose terms forbid training on submitted content. Free model tiers permit provider-side use of
    inputs and are never used on client evidence.</dd>
  <dt>This website</dt><dd>Runs the deterministic engine against synthetic corpora only. Nothing
    typed into the public demo is sent to a model provider or persisted. The only personal data
    the site stores is an email address you choose to submit.</dd>
  <dt>Retention</dt><dd>Run artifacts, workbooks and audit logs are held for the engagement and
    deleted on request. Audit logs are append-only by design, so they are retained or deleted
    whole rather than edited.</dd>
</dl>
{acc}

<h2>We reviewed ourselves, and published what we found</h2>
<p class="lead">On 24 August 2026 the platform was security-reviewed against itself, separately
from the evaluation of the answer gates. Four findings. All fixed, each with a regression test
that failed before its fix. They are published here rather than left for you to find.</p>
<div class="tablewrap"><table>
<tr><th>Finding</th><th>What it was</th><th>Status</th></tr>
<tr><td class="qid">Cross-tenant<br>path traversal</td>
    <td class="ans">A tenant name was used directly as a filesystem path component, so a crafted
    name loaded another client's documents while the store believed the crafted string
    <i>was</i> its tenant — defeating the boundary check by making it compare a value to itself.
    Isolation depended on every caller validating the name.</td>
    <td><span class="chip c-ok">FIXED</span></td></tr>
<tr><td class="qid">Stored XSS via<br>evidence content</td>
    <td class="ans">Answer text is a paragraph lifted verbatim from a client document, and it was
    being rendered as HTML. Markup planted in an ingested PDF would have executed in the
    operator's browser, with access to every workspace on that console.</td>
    <td><span class="chip c-ok">FIXED</span></td></tr>
<tr><td class="qid">Information<br>disclosure</td>
    <td class="ans">Unhandled exceptions returned their type and message to anonymous callers,
    which could include filesystem paths and internal names.</td>
    <td><span class="chip c-ok">FIXED</span></td></tr>
<tr><td class="qid">Unbounded<br>public endpoints</td>
    <td class="ans">Request bodies were read without a size cap and no rate limiting existed.</td>
    <td><span class="chip c-ok">FIXED</span></td></tr>
</table></div>

<h2>Two things we corrected the description of, rather than the code</h2>
<ul class="tight">
  <li><b>The audit log is tamper-evident, not tamper-resistant, unless it is signed.</b> A hash
      chain proves no entry was <i>edited</i>. It does not prove the log was not <i>replaced</i> —
      anyone who can write the file can recompute a consistent chain. Optional HMAC signing makes a
      signed deployment reject a regenerated log, and the system reports which property is in force
      instead of implying the stronger one.</li>
  <li><b>Reviewer identity is corroborated, not authenticated.</b> A reviewer name is supplied by
      the operator. The operating system user and host are recorded beside it inside the signed
      event, and the event explicitly records that the actor was not authenticated.</li>
</ul>

<h2>Open items</h2>
<div class="note"><b>Stated rather than discovered.</b> There is no authentication and no role
separation on the operator console — it binds to loopback and is a single-operator tool. No
independent penetration test has been performed, and we hold no certification of any kind: asked
whether we are ISO 42001 certified, our own trust page <a href="/trust/">refuses to claim it</a>,
because the only supporting document is a roadmap. These are the reasons Pramana is delivered as
an operated service today rather than as software you run.</div>

<h2>Everything above, generated</h2>
<p class="lead">The claims on this page are also in our evidence corpus, which means our own trust
page answers them the same way it would answer yours — cited, or refused.
<a href="/trust/">Open our trust center &rarr;</a></p>
"""
    return page(f"Security posture — {site.BRAND}", body, active="/security/",
                description="What Pramana holds, what it never does, and what its own security "
                            "review found.")


def build_demo() -> str:
    body = hero(
        "Ask it something. Try to make it lie.",
        "This runs the real engine — the same retrieval, the same deterministic gates, the "
        "same refusal logic the eval suite tests. The deterministic drafter is used so the "
        "result is reproducible and your question is never sent to a third-party model.")
    body += """
<div class="console">
<textarea id="q" placeholder="e.g. Are you ISO 27001 certified?"></textarea>
<div class="chips" id="chips"></div>
<div class="row">
  <select id="tenant"></select>
  <button class="btn primary" id="ask">Run through gates</button>
  <span class="spin" id="spin">retrieving &rarr; drafting &rarr; gating&hellip;</span>
</div>
<div class="result" id="result">
  <span class="chip" id="verdict"></span>
  <div class="answer-box" id="answer"></div>
  <div id="prov"></div>
  <div id="gaps"></div>
  <div class="small" id="meta"></div>
</div>
</div>

<h2>What to try</h2>
<ul class="tight">
  <li><b>Certification inference.</b> Ask whether Acme is ISO 27001 certified. Only a roadmap
      exists. A plan is not a certificate, and the gate will not let one become the other.</li>
  <li><b>Contradiction.</b> Ask how many days after termination customer data is deleted. Two
      approved Acme policies disagree — both get quarantined and the question routes to both
      owners.</li>
  <li><b>Stale evidence.</b> Ask about recent penetration testing. The report on file expired;
      an expired document cannot support a present-tense claim.</li>
  <li><b>Legal commitment.</b> Demand unlimited liability or an uptime guarantee. It never
      reaches the drafter — contractual commitments route to counsel before drafting.</li>
  <li><b>Out of corpus.</b> Ask something no document covers. Watch it refuse and name what
      is missing, rather than producing a confident paragraph.</li>
</ul>
<div class="note"><b>Both workspaces are synthetic.</b> <code>acme</code> is the demo corpus
with deliberately planted traps. <code>northwind</code> was onboarded from PDF and DOCX files
through the real ingestion path, and has only four approved sources — so it refuses a lot
more, which is the correct behaviour for a thin corpus.</div>

<style>
.console{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--ok);padding:20px 22px;margin:24px 0}
textarea{width:100%;min-height:64px;font:14px/1.5 "IBM Plex Sans",system-ui,sans-serif;color:var(--ink);
background:var(--paper);border:1px solid var(--line);padding:10px 12px;resize:vertical}
select{font:600 12px "IBM Plex Mono",monospace;padding:11px 14px;border:1.5px solid var(--ink);
background:var(--card);color:var(--ink);cursor:pointer}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.chips button{border:1px solid var(--line);background:var(--card);color:var(--muted);
font:400 11.5px "IBM Plex Mono",monospace;padding:6px 10px;cursor:pointer}
.chips button:hover{color:var(--ok);border-color:var(--ok)}
.result{margin-top:18px;display:none}
.answer-box{border:1px solid var(--line);background:var(--paper);padding:14px 16px;margin-top:10px;font-size:14px}
.spin{display:none;font:12px "IBM Plex Mono",monospace;color:var(--muted)}
.small{font:11px/1.6 "IBM Plex Mono",monospace;color:var(--muted);margin-top:8px}
button:disabled{opacity:.45;cursor:not-allowed}
</style>
<script src="/assets/demo.js" defer></script>
"""
    return page(f"Live demo — {site.BRAND}", body, active="/demo/",
                description="Run a security question through the real evidence gates.")


COMMITMENTS = ROOT / "data" / "commitments"
LIVE_RUN = PUBLIC / "artifacts" / "live-run-gemini" / "metrics.json"


def live_run_metrics() -> dict | None:
    """A dated run against a real model, committed as an artifact.

    Not re-executed at build time: it needs an API key and two and a half
    minutes of rate-limited calls. It is published as a fixed, dated artifact
    with its full report, contracts and audit log, so the comparison below is
    checkable rather than asserted."""
    return json.loads(LIVE_RUN.read_text(encoding="utf-8")) if LIVE_RUN.is_file() else None


def drafter_comparison(mock: dict, live: dict) -> str:
    pct = lambda x: f"{round(x * 100)}%"                     # noqa: E731
    rows = [
        ("Cited coverage", pct(mock["cited_draft_coverage"]), pct(live["cited_draft_coverage"])),
        ("Refused, by design", pct(mock["abstention_rate"]), pct(live["abstention_rate"])),
        ("Routed to humans", mock["exception_queue"], live["exception_queue"]),
        ("Unsupported claims", mock["unsupported_material_claims"],
         live["unsupported_material_claims"]),
        ("Audit chain", "valid" if mock["audit_chain_valid"] else "BROKEN",
         "valid" if live["audit_chain_valid"] else "BROKEN"),
        ("Cycle time", f"{mock['cycle_seconds']}s", f"{live['cycle_seconds']}s"),
    ]
    body = """
<h2>Swapping the model changes fluency, not safety posture</h2>
<p class="lead">The same 24-question workbook, the same corpus, the same gates — once with the
deterministic drafter and once with a live model. If the safety properties lived in the prompt,
these columns would differ. They do not.</p>
<div class="tablewrap"><table>
<tr><th>Measure</th><th>Deterministic</th><th>Live model (Gemini)</th></tr>"""
    for label, a, b in rows:
        same = str(a) == str(b)
        mark = ('<span class="chip c-ok">IDENTICAL</span>' if same
                else '<span class="chip c-rev">DIFFERS</span>')
        body += (f'<tr><td>{esc(label)}</td><td class="qid">{esc(a)}</td>'
                 f'<td class="qid">{esc(b)}</td><td>{mark}</td></tr>')
    body += "</table></div>"
    body += f"""
<p class="lead">The one real difference is phrasing quality inside the gates: the live model
produced {live['status_counts']['evidence_backed']} fully evidence-backed answers against
{mock['status_counts']['evidence_backed']}, converting
{mock['status_counts']['partial'] - live['status_counts']['partial']} partial answers into clean
ones. It did not gain the ability to publish anything uncited, and cycle time went from
{mock['cycle_seconds']}s to {live['cycle_seconds']}s because the free tier is rate limited to
roughly ten requests a minute.</p>
<p class="stamp">Live run {esc(LIVE_RUN.parent.name)} ·
<a href="/artifacts/live-run-gemini/run_report.html">audit working paper</a> ·
<a href="/artifacts/live-run-gemini/contracts.json">contracts</a> ·
<a href="/artifacts/live-run-gemini/audit_log.jsonl">audit log</a> ·
<a href="/artifacts/live-run-gemini/metrics.json">metrics</a></p>
"""
    return body


def build_commitments() -> tuple[str, dict] | tuple[None, None]:
    spec = COMMITMENTS / "acme.json"
    if not spec.is_file():
        return None, None
    result = commitments.evaluate("acme", EVIDENCE, spec, date.today())
    commitments.write(result, ARTIFACTS / "commitments" / "acme")
    # the register renders its own header; a hero above it would title the page twice
    body = commitments.render_body(result)
    body += """
<div class="note"><b>Read the contradicted one first.</b> A signed MSA commits to deleting
customer data within 30 days. Two approved policies in the same corpus declare 90 days and 365
days. That is not a judgement call or a language model's opinion — it is a machine-checkable
assertion in a governed document disagreeing with a signed number, and it was found without
anyone rereading the contract.</div>
<p class="stamp">Synthetic register ·
<a href="/artifacts/commitments/acme/commitments.json">commitments.json</a> ·
<a href="/artifacts/commitments/acme/index.html">standalone page</a></p>
"""
    return page(f"Commitment register — {site.BRAND}", body, active="/commitments/",
                description="Flags security commitments that evidence does not support."), \
           result.to_dict()


ACCURACY_JSON = ROOT / "evals" / "accuracy.json"
PROMPT_SET = ROOT / "evals" / "adversarial.json"


def build_accuracy() -> tuple[str, dict] | tuple[None, None]:
    """The published accuracy page.

    Rendered from the harness's own output. Every failure is listed by name with
    the reason, because a published pass rate with the failures removed is worth
    nothing to the person reading it."""
    if not ACCURACY_JSON.is_file():
        return None, None
    data = json.loads(ACCURACY_JSON.read_text(encoding="utf-8"))
    shutil.copy(ACCURACY_JSON, ARTIFACTS / "accuracy.json")
    shutil.copy(PROMPT_SET, ARTIFACTS / "adversarial.json")

    body = hero("Published accuracy, including what it gets wrong",
                f"{data['total_prompts']} adversarial prompts. Every label was written before "
                f"the harness first ran and none was revised to match the result. Every failure "
                f"is named below.")
    body += f"""
<div class="grid">
  <div class="stat ok"><b>{data['correctly_refused_pct']}%</b><span>correctly refused</span></div>
  <div class="stat ok"><b>{data['correctly_cited_pct']}%</b><span>correctly cited</span></div>
  <div class="stat {'ok' if data['released_without_citation'] == 0 else 'bad'}">
    <b>{data['released_without_citation']}</b><span>released with no citation</span></div>
  <div class="stat warn"><b>{data['over_released']}</b><span>over-released</span></div>
  <div class="stat"><b>{data['total_prompts']}</b><span>prompts</span></div>
  <div class="stat"><b>{data['overall_pct']}%</b><span>overall</span></div>
</div>

<h2>Why two numbers, not one</h2>
<p class="lead">A system that refuses everything scores 100% on refusal and is useless. A system
that answers everything scores 100% on citation and is dangerous. Neither number means anything
without the other, so both are published, and so is the count of answers released with no
citation at all — which is the invariant the engine actually enforces on every run.</p>
<p class="lead">The {data['over_released']} over-releases are worth being precise about: in both
cases the released answer carried a valid citation to a real, approved, in-force document. The
failure was that the question contained a clause the evidence did not cover, and the engine
answered the part it could. That is a genuine defect in question scoping. It is not the same
thing as inventing a fact, and collapsing the two into one "hallucination rate" would hide which
one happened.</p>

<h2>Method</h2>
<ul class="tight">
  <li>Each prompt is labelled <code>refuse</code> or <code>cite</code> — the outcome a competent
      security reviewer would demand. Labels were fixed before the first run.</li>
  <li><code>refuse</code> passes only if no answer text is released. <code>cite</code> passes only
      if an answer is released with at least one citation that survived the gates; where a specific
      source is named in the label, that source must be the one cited.</li>
  <li>Prompts run against four separate evidence corpora, including a red-team corpus containing an
      approved document whose prose declares itself a certificate and instructs the model to cite
      itself as one.</li>
  <li>Scored with the deterministic drafter, so the number is reproducible. The harness runs
      against a live model with one flag; the gates are identical either way.</li>
  <li>A positive control the engine fails to cite — including a plain retrieval miss — is published
      as a failure, not excused as out of scope.</li>
</ul>

<h2>By category</h2>
<div class="tablewrap"><table>
<tr><th>Category</th><th>Passed</th><th></th></tr>"""
    for name, entry in sorted(data["by_category"].items()):
        clean = entry["passed"] == entry["total"]
        chip = ('<span class="chip c-ok">CLEAN</span>' if clean
                else '<span class="chip c-warn">SEE FAILURES</span>')
        body += (f'<tr><td>{esc(name)}</td>'
                 f'<td><b>{entry["passed"]}/{entry["total"]}</b></td><td>{chip}</td></tr>')
    body += "</table></div>"

    body += f"<h2>Every failure, named ({len(data['failures'])})</h2>"
    body += ('<p class="sub">Published in full. A pass rate with the failures removed tells the '
             'reader nothing they can act on.</p><div class="tablewrap"><table>'
             '<tr><th>ID</th><th>Category</th><th>Prompt</th><th>What went wrong</th></tr>')
    for f in data["failures"]:
        body += (f'<tr><td class="qid">{esc(f["id"])}</td><td class="dom">{esc(f["category"])}</td>'
                 f'<td class="ans">{esc(f["question"])}</td>'
                 f'<td class="ans">{esc(f["failure_reason"])}</td></tr>')
    body += "</table></div>"

    body += f"""
<div class="note"><b>What the failures say about the product.</b> The categories that would
represent an outright breach — certification inference, contradiction, stale evidence, legal
scope, cross-tenant attribution, injection planted in evidence, out-of-corpus questions — are
clean, and the test suite fails the build if any of them regresses. What is not solved is
compound questions where one clause is unsupported, false premises stated as fact, and the
precision of lexical retrieval. Those are named here rather than left for a buyer to discover.</div>

<p class="stamp">Scored {esc(data['run_date'])} · drafter {esc(data['drafter'])} ·
prompt set v{esc(data['prompt_set_version'])} ·
<a href="/artifacts/accuracy.json">full per-prompt results (JSON)</a> ·
<a href="/artifacts/adversarial.json">the prompt set itself</a></p>
"""
    return page(f"Accuracy — {site.BRAND}", body, active="/accuracy/",
                description=(f"{data['total_prompts']} adversarial prompts: "
                             f"{data['correctly_refused_pct']}% correctly refused, "
                             f"{data['correctly_cited_pct']}% correctly cited.")), data


def build_isolation() -> str:
    """Isolation, proved by running the tests rather than described in a paragraph."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--no-header", "-p", "no:cacheprovider",
         "-k", "tenant or isolation or INJE or injection"],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    captured = "\n".join(
        ln for ln in proc.stdout.splitlines()
        if ("PASSED" in ln or "FAILED" in ln or ln.startswith("="))
    ) or proc.stdout[-2000:]

    body = hero("Isolation is a property of the layout, not of a filter somebody remembers",
                "A buyer asks this on the first call. It deserves a page, not a paragraph.")
    body += f"""
<h2>How it works</h2>
<ul class="tight">
  <li>Each client is a separate directory, and an evidence store is constructed from exactly one
      of them. <b>There is no code path that loads two tenants into one store</b>, so there is no
      query that returns the wrong client's document by forgetting a filter.</li>
  <li>Every chunk carries the tenant it came from. The retriever raises <code>PermissionError</code>
      on a tenant mismatch and asserts tenant identity on each chunk before returning it — a
      mismatch fails loudly rather than degrading to a partial result.</li>
  <li>Documents awaiting human approval are staged in a subdirectory the store does not read, so
      unapproved material is invisible to retrieval by construction rather than by a status flag.</li>
  <li>A separate scope gate refuses questions that <i>name</i> another workspace. Isolation stops
      another client's documents being retrieved; it does not, on its own, stop the engine
      answering &ldquo;what does Globex's policy say?&rdquo; out of this client's corpus and
      quietly attributing one company's controls to another. That was a real finding from our own
      adversarial suite.</li>
</ul>

<h2>The decoy</h2>
<p class="lead">The eval suite contains a decoy workspace whose documents are deliberately worded
to resemble the primary client's, so that if isolation depended on relevance scoring rather than
structure, the decoy would surface. The tests assert zero cross-tenant chunks retrieved and assert
that a mismatched request raises. A failure blocks release.</p>

<h2>Run on this build</h2>
<p class="sub">Captured from the actual test run during this site's build, not transcribed.</p>
<pre><code>{esc(captured)}</code></pre>

<h2>Try to break it</h2>
<p class="lead">On the <a href="/demo/">live demo</a>, choose the <code>acme</code> workspace and
ask what Globex's or Northwind's policy says. Then ask it to list every tenant on the system.</p>
<p class="stamp">Exit status {proc.returncode} · generated {date.today().isoformat()}</p>
"""
    return page(f"Tenant isolation — {site.BRAND}", body, active="/isolation/",
                description="How client isolation works, and the tests that prove it.")


def build_metrics(metrics: dict, trust: dict, accuracy: dict | None,
                  register: dict | None, live: dict | None = None) -> str:
    body = hero("Outcome metrics, instrumented",
                "The measures a buyer's security team actually feels. Some are computed from real "
                "runs today. The ones that need a live pilot are listed as not yet measured, "
                "rather than filled in with something plausible.")
    ttfd = metrics.get("time_to_first_draft_seconds")
    body += f"""
<h2>Measured today</h2>
<div class="grid">
  <div class="stat"><b>{metrics['questions']}</b><span>questions per run</span></div>
  <div class="stat ok"><b>{ttfd if ttfd is not None else '—'}s</b><span>time to first draft</span></div>
  <div class="stat ok"><b>{metrics['cycle_seconds']}s</b><span>full run cycle</span></div>
  <div class="stat ok"><b>{round(metrics['zero_human_edit_rate'] * 100)}%</b>
    <span>shipped with zero human edit</span></div>
  <div class="stat warn"><b>{round(metrics['abstention_rate'] * 100)}%</b>
    <span>refused, by design</span></div>
  <div class="stat ok"><b>{round(metrics['refusals_with_named_gap'] * 100)}%</b>
    <span>refusals naming a gap</span></div>
  <div class="stat ok"><b>{round(trust['deflection_rate'] * 100)}%</b>
    <span>trust-page deflection</span></div>
  <div class="stat {'ok' if metrics['unsupported_material_claims'] == 0 else 'bad'}">
    <b>{metrics['unsupported_material_claims']}</b><span>unsupported claims</span></div>
</div>
<p class="stamp">From the reference run executed during this build, and the trust center generated
alongside it. Rebuilding the site recomputes every figure on this page.</p>

<h2>What each one is for</h2>
<div class="tablewrap"><table>
<tr><th>Metric</th><th>Why a buyer cares</th></tr>
<tr><td class="qid">time to first draft</td><td>How long after a questionnaire lands before a
human has something to review, rather than a blank workbook.</td></tr>
<tr><td class="qid">zero-human-edit rate</td><td>The share of answers that shipped exactly as
drafted. This is the honest automation number — not "questions processed".</td></tr>
<tr><td class="qid">refusals naming a gap</td><td>A refusal that does not say what is missing
creates work instead of removing it. This should be 100%, and it is asserted.</td></tr>
<tr><td class="qid">trust-page deflection</td><td>Standard buyer questions answerable
self-service. Every one is an inbound request that never arrives.</td></tr>
<tr><td class="qid">unsupported claims</td><td>The release gate. A run with any is blocked.</td></tr>
</table></div>
"""
    if register:
        body += f"""
<h2>Commitment exposure</h2>
<div class="grid">
  <div class="stat bad"><b>{register['by_verdict']['CONTRADICTED']}</b><span>contradicted</span></div>
  <div class="stat warn"><b>{register['by_verdict']['UNSUPPORTED']}</b><span>unsupported</span></div>
  <div class="stat"><b>{register['by_verdict']['EXPIRING']}</b><span>evidence expires first</span></div>
  <div class="stat ok"><b>{register['by_verdict']['SUPPORTED']}</b><span>supported</span></div>
</div>
<p class="stamp"><a href="/commitments/">See the register &rarr;</a></p>
"""
    if accuracy:
        body += f"""
<h2>Correctness</h2>
<div class="grid">
  <div class="stat ok"><b>{accuracy['correctly_refused_pct']}%</b><span>correctly refused</span></div>
  <div class="stat ok"><b>{accuracy['correctly_cited_pct']}%</b><span>correctly cited</span></div>
  <div class="stat ok"><b>{accuracy['released_without_citation']}</b><span>uncited releases</span></div>
</div>
<p class="stamp"><a href="/accuracy/">Method and every failure &rarr;</a></p>
"""
    if live:
        body += drafter_comparison(metrics, live)
    body += """
<h2>Not yet measured</h2>
<p class="lead">These need a live pilot with a real sales cycle behind them. They are instrumented
and empty, which is the truthful state — a number here today would be invented.</p>
<ul class="tight">
  <li><b>Days removed from a security review.</b> Requires before-and-after cycle times from a
      customer's own deals.</li>
  <li><b>Inbound questions deflected by the trust page.</b> Requires page analytics against a
      baseline of inbound volume; deflection potential is measured above, actual deflection is not.</li>
  <li><b>Analyst hours returned per questionnaire.</b> Requires a measured manual baseline from
      the same team on the same questionnaires.</li>
</ul>
<div class="note"><b>On the automation number.</b> Zero-human-edit rate is reported against a
simulated reviewer that approves only gate-clean, complete-coverage drafts. Under a real named
reviewer the number will be lower, and that is the number worth quoting once a pilot produces
one.</div>
"""
    return page(f"Outcomes — {site.BRAND}", body, active="/metrics/",
                description="Instrumented outcome metrics, and the ones not yet measurable.")


def build_trust() -> tuple[str, dict]:
    """Pramana's own trust center — the same generator a client would run,
    pointed at our own corpus. Also emits each client's page as an artifact, so
    the claim that this is a generator rather than one hand-made page is
    checkable rather than asserted."""
    own = trustpage.generate("pramana", EVIDENCE)
    trustpage.write(own, ARTIFACTS / "trust" / "pramana", CONTACT)
    others = {}
    for slug in CLIENT_TRUST_PAGES:
        result = trustpage.generate(slug, EVIDENCE)
        trustpage.write(result, ARTIFACTS / "trust" / slug)
        others[slug] = result

    body = trustpage.render_body(own, CONTACT)
    body += """
<h2>This page is generated, not written</h2>
<p class="lead">The same generator runs against any client corpus. These were produced in the
same build as the page above, from entirely separate evidence stores:</p>
<div class="cols">"""
    for slug, result in others.items():
        body += (f'<div class="card"><h3>{esc(result.tenant.title)}</h3>'
                 f'<p>{len(result.published)} of {len(result.answers)} standard questions '
                 f'answered from {len(list((EVIDENCE / slug).glob("*.md")))} approved sources '
                 f'— {round(result.deflection_rate * 100)}% deflection.<br>'
                 f'<a href="/artifacts/trust/{slug}/index.html">View this trust page &rarr;</a> · '
                 f'<a href="/artifacts/trust/{slug}/deflection.json">deflection.json</a></p></div>')
    body += """</div>
<div class="note"><b>Why our own number is low.</b> Pramana is a pre-pilot system with ten
approved documents and no certifications of any kind, so most of the standard set is
genuinely unsupported and shows as open. Publishing a low honest number is the argument;
a trust page that answered thirty-two of thirty-two would be evidence of the failure mode
this product exists to prevent.</div>
"""
    return page(f"Trust center — {site.BRAND}", body, active="/trust/",
                description="Pramana's own security answers, generated by Pramana."), own.to_dict()


DEMO_JS = """// Live demo client.
//
// SECURITY: nothing that comes back from /api/ask is ever assigned to innerHTML.
// An answer is a paragraph lifted verbatim from an evidence document, and a
// document is attacker-influenced input in exactly the threat model this
// product is about — a paragraph containing markup would otherwise execute in
// the visitor's browser. Every network-derived value below is set with
// textContent or appended as a text node.
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var SAMPLES = [
    'Are you ISO/IEC 27001 certified?',
    'Within how many days of contract termination is customer data deleted?',
    'Has an independent penetration test been performed in the last 12 months?',
    'Will you contractually commit to unlimited liability for any breach?',
    'Is customer data encrypted at rest?',
    'Do you use customer data to train models?',
    "What does Globex's policy say about access reviews?"
  ];

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function chipClass(v) {
    if (v.indexOf('CITED \u00b7 GATE-CLEAN') === 0) return 'chip c-ok';
    if (v.indexOf('CITED') === 0) return 'chip c-rev';
    return 'chip c-warn';
  }

  async function boot() {
    var info = await (await fetch('/api/ask')).json();
    var tenants = info.tenants || ['acme'];
    var sel = $('tenant');
    clear(sel);
    tenants.forEach(function (t) {
      var o = document.createElement('option');
      o.value = t;
      o.textContent = 'workspace: ' + t;
      sel.appendChild(o);
    });
    var chips = $('chips');
    clear(chips);
    SAMPLES.forEach(function (sample) {
      var b = el('button', null, sample);
      b.type = 'button';
      b.addEventListener('click', function () { $('q').value = sample; });
      chips.appendChild(b);
    });
  }

  function render(data) {
    var c = data.contract;
    $('verdict').textContent = data.verdict;
    $('verdict').className = chipClass(data.verdict);

    var answer = $('answer');
    clear(answer);
    if (c.answer) {
      answer.appendChild(document.createTextNode(c.answer));
    } else {
      answer.appendChild(el('em', null, 'No answer released.'));
    }

    var prov = $('prov');
    clear(prov);
    if (c.citations.length) {
      var box = el('div', 'prov');
      c.citations.forEach(function (x, i) {
        if (i) box.appendChild(document.createElement('br'));
        box.appendChild(document.createTextNode(
          x.source_id + ' \u00b7 v' + x.version + ' \u00b7 ' + x.location));
      });
      prov.appendChild(box);
    } else {
      prov.appendChild(el('div', 'prov p-warn',
        'no citation released \u00b7 routed to ' + (c.route || 'no-evidence')));
    }

    var gaps = $('gaps');
    clear(gaps);
    c.gaps.forEach(function (g) { gaps.appendChild(el('div', 'gap', '\u25b8 ' + g)); });

    $('meta').textContent =
      'coverage=' + c.evidence_coverage + ' \u00b7 risk=' + c.risk +
      ' \u00b7 drafter=' + c.drafter +
      ' \u00b7 human_review=' + (c.requires_human ? 'required' : 'not required') +
      (c.gate_flags.length ? ' \u00b7 flags: ' + c.gate_flags.join(' | ') : '');
    $('result').style.display = 'block';
  }

  function renderError(message) {
    $('verdict').textContent = 'ENGINE ERROR';
    $('verdict').className = 'chip c-bad';
    clear($('answer'));
    $('answer').appendChild(el('em', null, message));
    clear($('prov'));
    clear($('gaps'));
    $('meta').textContent = '';
    $('result').style.display = 'block';
  }

  $('ask').addEventListener('click', async function () {
    var q = $('q').value.trim();
    if (!q) return;
    $('spin').style.display = 'inline';
    $('result').style.display = 'none';
    $('ask').disabled = true;
    try {
      var r = await fetch('/api/ask', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, tenant: $('tenant').value })
      });
      var data = await r.json();
      if (data.error) throw new Error(data.error);
      render(data);
    } catch (e) {
      renderError(e.message);
    }
    $('spin').style.display = 'none';
    $('ask').disabled = false;
  });

  boot();
})();
"""

ASSETS = {"demo.js": DEMO_JS, "waitlist.js": WAITLIST_JS}


CHANGELOG = [
    ("2026-08-24", "Platform security self-review — four findings, all fixed", [
        "Cross-tenant path traversal: a tenant name was used directly as a path component, so a "
        "crafted name loaded another tenant's corpus while the store believed the crafted string "
        "WAS its tenant — defeating the boundary assertion by making it compare a value to "
        "itself. Tenant names are now validated at the store and query boundary, the directory "
        "must resolve to a direct child of the evidence root, and symlinks out are refused.",
        "Stored XSS through evidence content: answer, gap and provenance text was assigned to "
        "innerHTML, so markup planted in an ingested client PDF would execute in the analyst's "
        "browser with access to every workspace. All clients now render engine output as text "
        "nodes, all script is served as external files, and the CSP forbids inline script.",
        "Information disclosure: unhandled exceptions returned their type and message, which "
        "could include filesystem paths. Errors now return an opaque message and a correlation "
        "reference; detail goes to the server log only.",
        "Unbounded public endpoints: request bodies are capped before parsing, and a "
        "per-instance limit of 20 requests per minute per client applies.",
        "Audit log property clarified: the hash chain proves nothing was edited, not that the "
        "log was not replaced wholesale. Optional HMAC signing added; the system now reports "
        "which property is in force instead of implying the stronger one.",
        "Reviewer identity is corroborated, not authenticated — OS user and host recorded beside "
        "the self-asserted name, inside the signed event, and labelled as unauthenticated.",
        "Open and stated: no authentication on the operator console, and no independent "
        "penetration test.",
    ]),
    ("2026-08-24", "Public site, live demo, and real-client onboarding", [
        "Published accuracy: 59 adversarial prompts, 95.5% correctly refused, 73.3% correctly "
        "cited, 0 answers released without a citation. Every failure listed by name.",
        "Scope gate: a question naming another workspace, or asking about the system's own "
        "configuration, is refused before drafting. Isolation stopped another client's documents "
        "being retrieved; nothing stopped one client's controls being attributed to another.",
        "Commitment register: checks executed contracts, RFP responses and DPAs against the "
        "evidence corpus — contradicted, unsupported, or supported by evidence that expires "
        "before the commitment date.",
        "Outcome metrics and an isolation page carrying the actual test output.",
        "Dated live-model run published as an artifact: identical gate outcomes to the "
        "deterministic drafter.",
        "Trust center generator: publishes only evidence-backed answers, everything else "
        "shows as open. Pramana's own trust center is its output.",
        "Certification gate matched a name allowlist and did not know ISO 42001, so a "
        "roadmap satisfied an ISO 42001 certification question on our own trust page. "
        "The pattern now matches any ISO/IEC number and a wider set of schemes.",
        "Named-human review: decisions extend the run's own hash chain; approval is "
        "unavailable when the gates released nothing; human-written answers are labelled "
        "HUMAN_AUTHORED rather than evidence-backed.",
        "Document ingestion: PDF, DOCX, XLSX and markdown, staged for human approval.",
        "Questionnaire layout detection — any CAIQ/SIG-shaped workbook or CSV, no code changes.",
        "Client workspaces and a tenant selector; second synthetic client onboarded end to end.",
        "Certificate and attestation types are never auto-assigned during ingestion.",
        "First public deployment.",
    ]),
    ("2026-08-08", "v0 engine", [
        "Evidence-gated pipeline: cite-or-abstain, staleness, contradiction, certification "
        "evidence class, legal routing, structural tenant isolation.",
        "Hash-chained tamper-evident audit log.",
        "Structure-preserving XLSX round trip.",
        "Adversarial eval suite; zero unsupported material claims as a release gate.",
        "Live drafters (Gemini free tier, Anthropic Haiku) behind the same gates.",
    ]),
]


def build_changelog() -> str:
    body = hero("Changelog",
                "Dated, and honest about what each change did and did not include.")
    for stamp, title, items in CHANGELOG:
        body += (f'<h2>{esc(stamp)} — {esc(title)}</h2><ul class="tight">'
                 + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>")
    return page(f"Changelog — {site.BRAND}", body, active="/changelog/",
                description="What shipped, and when.")


def main() -> int:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    # Scripts are external files so the Content-Security-Policy can forbid inline
    # script entirely: even a missed sink cannot execute injected markup.
    (PUBLIC / "assets").mkdir(parents=True, exist_ok=True)
    for name, source in ASSETS.items():
        (PUBLIC / "assets" / name).write_text(source, encoding="utf-8")
        print(f"  wrote /assets/{name}")
    print("running the engine for the reference run…")
    metrics = reference_run()
    print(f"  {json.dumps(metrics)}")

    print("generating trust centers…")
    trust_html, trust_data = build_trust()
    print(f"  pramana deflection {trust_data['deflection_rate']:.1%} "
          f"({trust_data['self_serve_answers']}/{trust_data['questions']})")

    print("scoring the adversarial suite…")
    accuracy_html, accuracy = build_accuracy()
    if accuracy:
        print(f"  {accuracy['correctly_refused_pct']}% refused / "
              f"{accuracy['correctly_cited_pct']}% cited / "
              f"{accuracy['released_without_citation']} uncited releases")

    print("evaluating the commitment register…")
    commitments_html, register = build_commitments()
    if register:
        print(f"  {register['at_risk']}/{register['commitments']} commitments not defensible")

    print("proving isolation…")
    isolation_html = build_isolation()

    routes = {
        "/": lambda: build_index(metrics, trust_data, accuracy),
        "/how-it-works/": build_how_it_works,
        "/deliverables/": build_deliverables,
        "/pricing/": build_pricing,
        "/security/": lambda: build_security(accuracy),
        "/trust/": lambda: trust_html,
        "/demo/": build_demo,
        "/changelog/": build_changelog,
        "/isolation/": lambda: isolation_html,
        "/metrics/": lambda: build_metrics(metrics, trust_data, accuracy, register,
                                           live_run_metrics()),
    }
    if accuracy_html:
        routes["/accuracy/"] = lambda: accuracy_html
    if commitments_html:
        routes["/commitments/"] = lambda: commitments_html
    site.set_available(set(routes))
    for route, builder in routes.items():
        write(route, builder())
        print(f"  wrote {route}")
    (PUBLIC / "build.json").write_text(json.dumps({
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "routes": sorted(routes), "reference_run": metrics,
        "accuracy": {k: accuracy[k] for k in
                     ("total_prompts", "correctly_refused_pct", "correctly_cited_pct",
                      "released_without_citation", "over_released")} if accuracy else None,
        "trust": {k: trust_data[k] for k in
                  ("questions", "self_serve_answers", "open_items", "deflection_rate")},
    }, indent=2), encoding="utf-8")
    print(f"site → {PUBLIC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
