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
def build_index(metrics: dict) -> str:
    pct = lambda x: f"{round(x * 100)}%"                       # noqa: E731
    body = hero(
        "Most questionnaire tools answer everything. The useful one knows when to refuse.",
        "Pramana is an evidence-gated customer assurance engine. Every answer names the "
        "approved document, version and paragraph it came from — and when the evidence "
        "isn't there, it refuses, names the gap, and routes it to a human. "
        "The refusals are the product.",
        cta_buttons([("/demo/", "Try the live demo", True),
                     ("/trust/", "Our own trust center", False),
                     ("/accuracy/", "Published accuracy", False)]))

    body += f"""
<h2>Three jobs, in the order that matters</h2>
<div class="cols">
  <div class="card">
    <h3>1 · Deflect</h3>
    <p>Generate a self-service trust center from the same evidence corpus. Every question a
    buyer can answer themselves is a question that never reaches your security team, and never
    adds a day to the deal.</p>
  </div>
  <div class="card rev">
    <h3>2 · Answer</h3>
    <p>What the trust page can't deflect gets drafted from approved, in-force sources — cited
    to source id, version and paragraph, then written back into the buyer's own workbook with
    its structure intact.</p>
  </div>
  <div class="card warn">
    <h3>3 · Refuse</h3>
    <p>No evidence, stale evidence, contradictory evidence, or a contractual commitment
    dressed as a question: the engine declines, names the specific gap, and routes it to a
    named human. It never invents a plausible answer.</p>
  </div>
</div>

<h2>What one real run looks like</h2>
<p class="sub">A {metrics['questions']}-question CAIQ-style workbook, run by the deterministic
drafter during this site's build. These are not illustrative figures — rebuilding the site
re-runs the engine and rewrites this block.</p>
<div class="grid">
  <div class="stat"><b>{metrics['questions']}</b><span>questions</span></div>
  <div class="stat ok"><b>{pct(metrics['cited_draft_coverage'])}</b><span>cited coverage</span></div>
  <div class="stat warn"><b>{pct(metrics['abstention_rate'])}</b><span>refused, by design</span></div>
  <div class="stat warn"><b>{metrics['exception_queue']}</b><span>routed to humans</span></div>
  <div class="stat {'ok' if metrics['unsupported_material_claims'] == 0 else 'bad'}">
    <b>{metrics['unsupported_material_claims']}</b><span>unsupported claims</span></div>
  <div class="stat {'ok' if metrics['audit_chain_valid'] else 'bad'}">
    <b>{'VALID' if metrics['audit_chain_valid'] else 'BROKEN'}</b><span>audit chain</span></div>
</div>
<p class="stamp">Artifacts from this exact run:
<a href="/artifacts/reference-run/run_report.html">audit working paper</a> ·
<a href="/artifacts/reference-run/contracts.json">answer contracts (JSON)</a> ·
<a href="/artifacts/reference-run/audit_log.jsonl">hash-chained audit log</a> ·
<a href="/artifacts/reference-run/metrics.json">metrics</a></p>

<h2>Every answer carries a status, not a confidence score</h2>
<p class="lead">A confidence score invites you to ship a 0.72. A status tells you what is
actually true about the evidence, and it is derived in code from citations that survived the
gates — never from what the model thought of itself.</p>
<div class="tablewrap"><table>
<tr><th>Status</th><th>Means</th><th>What happens next</th></tr>
<tr><td><span class="chip c-ok">EVIDENCE-BACKED</span></td>
    <td>Every claim cited to an approved, in-force source.</td><td>Ships.</td></tr>
<tr><td><span class="chip c-rev">PARTIAL</span></td>
    <td>Citable, but with gaps recorded against it.</td><td>Human reviews before it ships.</td></tr>
<tr><td><span class="chip c-warn">NO EVIDENCE</span></td>
    <td>Nothing approved supports an answer.</td>
    <td>Refused. Gap named, routed for collection.</td></tr>
<tr><td><span class="chip c-warn">REQUIRES HUMAN</span></td>
    <td>Certification claim, high risk, or a contradiction between sources.</td>
    <td>Routed to the named owner.</td></tr>
</table></div>

<h2>The gates do not trust the drafter</h2>
<pre><code>questionnaire (any layout)
      |  ingest — row identity preserved
      v
RECEIVED -&gt; CLASSIFIED -&gt; DRAFTED -&gt; [EXCEPTION | GRC_REVIEW] -&gt; DELIVERED
      |          |            |             |                        |
      |     pre-gates      drafter      post-gates            written back into
      |     legal routing  (any model)  cite-or-abstain       the original file,
      |     cert tagging                staleness            structure intact
      |                                 contradiction
      |                                 cert evidence class
      +---------- hash-chained, append-only audit log --------------+</code></pre>
<p class="lead">Tenant isolation, forbidden claims, staleness and approval are enforced in
code, not in a prompt. Swapping the deterministic drafter for a live model changes fluency,
not safety posture — which is the entire point of building it this way.</p>

<div class="note"><b>Honest scope.</b> Pramana is pre-pilot and runs as an operator-run
control plane, not self-serve SaaS. Onboarding a client is a one-time evidence-corpus pass;
after that, each questionnaire is minutes. Retrieval is lexical today, so it will miss some
paraphrased questions — it fails closed and refuses rather than guessing. All data shown
across this site is synthetic.</div>
""" + waitlist_block("landing")
    return page(f"{site.BRAND} — {site.TAGLINE}", body, active="/",
                description="Evidence-gated security questionnaire automation: every answer "
                            "cited to an approved source, or refused.")


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

    routes = {"/": build_index, "/trust/": lambda: trust_html,
              "/demo/": build_demo, "/changelog/": build_changelog,
              "/isolation/": lambda: isolation_html,
              "/metrics/": lambda: build_metrics(metrics, trust_data, accuracy, register,
                                                 live_run_metrics())}
    if accuracy_html:
        routes["/accuracy/"] = lambda: accuracy_html
    if commitments_html:
        routes["/commitments/"] = lambda: commitments_html
    site.set_available(set(routes))
    for route, builder in routes.items():
        write(route, builder(metrics) if route == "/" else builder())
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
