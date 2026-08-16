"""Hosted HTML pages: workspace and review queue, on the brand system.

Same pattern as ui/app.py: Python string templates + inline JS, zero build
step, brand.stylesheet() inlined so pages make no external requests.
"""
from __future__ import annotations

import html as _html
import json

from .. import brand
from .demo_questions import DEMO_QUESTIONS

HOSTED_CSS = """
.console{background:var(--surface-card);border:1px solid var(--line-1);border-left:2px solid var(--signal);
border-radius:var(--radius-2);padding:20px 22px;margin:20px 0}
input[type=text],input[type=date],input[type=email]{width:100%;font-family:var(--font-sans);font-size:14px;
color:var(--text-primary);background:var(--surface-sunken);border:1px solid var(--line-1);
border-radius:var(--radius-1);padding:10px 12px}
input:focus,select:focus,textarea:focus{outline:1px solid var(--focus-ring);outline-offset:0}
label{display:block;font-family:var(--font-mono);font-size:10px;letter-spacing:0.13em;
text-transform:uppercase;color:var(--text-tertiary);margin:14px 0 6px}
select,button{font-family:var(--font-mono);font-size:11px;letter-spacing:0.1em;text-transform:uppercase;
padding:10px 15px;border:1px solid var(--line-2);border-radius:var(--radius-1);
background:var(--surface-raised);color:var(--text-primary);cursor:pointer}
button.primary{background:var(--signal);color:var(--signal-ink);border-color:var(--signal)}
button.primary:hover{background:var(--signal-bright)}
button:disabled{opacity:.4;cursor:not-allowed}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:14px}
.grid2{display:grid;gap:0 18px;grid-template-columns:1fr 1fr}
@media(max-width:640px){.grid2{grid-template-columns:1fr}}
.doc{display:flex;gap:12px;align-items:baseline;padding:10px 0;border-bottom:1px solid var(--line-1);
font-size:13.5px;flex-wrap:wrap}
.doc:last-child{border-bottom:0}
.doc .sid{font-family:var(--font-mono);font-size:11px;color:var(--signal)}
.doc .meta{font-family:var(--font-mono);font-size:10.5px;color:var(--text-faint)}
.err{color:var(--status-critical);font-family:var(--font-mono);font-size:12px;margin-top:10px;
white-space:pre-wrap}
.ok-note{color:var(--status-ok);font-family:var(--font-mono);font-size:12px;margin-top:10px}
.runrow{display:flex;gap:14px;align-items:center;padding:12px 0;border-bottom:1px solid var(--line-1);
flex-wrap:wrap;font-family:var(--font-mono);font-size:12px}
.runrow:last-child{border-bottom:0}
.filelink{font-family:var(--font-mono);font-size:11px;letter-spacing:0.06em;color:var(--signal)}
.qcard{background:var(--surface-card);border:1px solid var(--line-1);border-radius:var(--radius-2);
padding:18px 20px;margin-bottom:14px}
.qcard h3{font-size:17px;margin:6px 0 10px}
.qcard .body{font-size:14px;color:var(--text-primary);background:var(--surface-sunken);
border-radius:var(--radius-1);padding:12px 14px;margin:10px 0}
.gap{color:var(--status-warn);font-family:var(--font-mono);font-size:11.5px;line-height:1.7}
.prov{font-family:var(--font-mono);font-size:10.5px;color:var(--text-tertiary);
border-left:2px solid var(--status-ok);padding-left:9px;margin-top:8px}
textarea{width:100%;min-height:52px;font-family:var(--font-sans);font-size:13.5px;
color:var(--text-primary);background:var(--surface-sunken);border:1px solid var(--line-1);
border-radius:var(--radius-1);padding:10px 12px;resize:vertical}
.quota{font-family:var(--font-mono);font-size:11px;color:var(--text-faint)}
progress{width:100%;height:4px;accent-color:var(--signal)}
"""


def _page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex">'
            f"<title>{_html.escape(title)}</title>"
            f"<style>{brand.stylesheet(HOSTED_CSS)}</style></head>"
            f'<body><div class="wrap">{body}</div></body></html>')


TYPE_OPTIONS = "".join(
    f'<option value="{t}">{t}</option>'
    for t in ("policy", "standard", "plan", "report", "attestation",
              "certificate", "roadmap", "register"))

QUESTION_LIST = "".join(
    f'<div class="doc"><span class="sid">{qid}</span>'
    f'<span style="color:var(--text-secondary)">{_html.escape(text)}</span></div>'
    for qid, _dom, text in DEMO_QUESTIONS)


def workspace(slug: str, org: str) -> str:
    body = f"""
<header>
<div class="eyebrow"><b>TrustOps</b> / workspace / {_html.escape(slug)}</div>
<h1>{_html.escape(org)}</h1>
<div class="runmeta">Evidence stays in this workspace. Embeddings run on our server;
only a question and its retrieved excerpts ever reach the drafting model.
This workspace and everything in it is deleted 14 days after signup.</div>
</header>

<div class="seclabel"><span class="idx">01</span><span class="label">Evidence</span><span class="rule"></span></div>
<h2>Upload your documents</h2>
<p class="sub">Policies, standards, reports, certificates. PDF, DOCX, MD, or TXT, up to 5MB each,
20 per workspace. Answers can only cite documents you attest are approved and current.</p>
<div class="console">
<form id="upform">
<label>File</label><input type="file" id="file" name="file" accept=".pdf,.docx,.md,.txt" required>
<div class="grid2">
<div><label>Title</label><input type="text" name="title" required maxlength="120" placeholder="Information Security Policy"></div>
<div><label>Type</label><select name="type">{TYPE_OPTIONS}</select></div>
<div><label>Version</label><input type="text" name="version" placeholder="1.0"></div>
<div><label>Owner email</label><input type="email" name="owner" required placeholder="security@yourco.com"></div>
<div><label>Effective date</label><input type="date" name="effective_date" required></div>
<div><label>Expiry date</label><input type="date" name="expiry_date" required></div>
</div>
<label>Topics (comma separated, improves retrieval)</label>
<input type="text" name="topics" placeholder="encryption, key management, data at rest">
<div class="row" style="align-items:flex-start">
<label style="margin:0;display:flex;gap:8px;align-items:center;text-transform:none;letter-spacing:0;font-size:12.5px;color:var(--text-secondary)">
<input type="checkbox" name="attested" style="width:auto"> I attest this document is approved and current in my organization</label>
</div>
<div class="row"><button class="primary" type="submit" id="upbtn">Upload</button>
<button type="button" id="seedbtn">Seed with sample evidence pack</button>
<span class="quota" id="doccount"></span></div>
<div class="err" id="uperr"></div><div class="ok-note" id="upok"></div>
</form>
<div id="docs" style="margin-top:18px"></div>
</div>

<div class="seclabel"><span class="idx">02</span><span class="label">The run</span><span class="rule"></span></div>
<h2>Ten questions, answered or refused</h2>
<p class="sub">Every answer must survive the deterministic gates: citation or abstention, staleness,
contradiction, certification evidence class, legal routing. A refusal names its gap.</p>
<div class="console">{QUESTION_LIST}
<div class="row"><button class="primary" id="runbtn">Run the questionnaire</button>
<span class="quota" id="quota"></span></div>
<div id="runstat" style="margin-top:14px"></div>
<div class="err" id="runerr"></div>
<div id="runs" style="margin-top:10px"></div>
</div>

<div class="seclabel"><span class="idx">03</span><span class="label">Review</span><span class="rule"></span></div>
<h2>Named review before anything ships</h2>
<p class="sub">Nothing reaches DELIVERED without a named reviewer and a note in the audit chain.
<a class="filelink" href="/t/{slug}/review">Open the review queue</a></p>

<footer>TrustOps hosted demo / data deleted after 14 days / <a class="filelink" href="mailto:dhruv.shahi07@gmail.com?subject=TrustOps%20pilot">book a pilot</a></footer>
"""
    js = """
<script>
const slug=location.pathname.split('/')[2];
const $=id=>document.getElementById(id);
async function refresh(){
  const s=await (await fetch(`/t/${slug}/api/state`)).json();
  $('doccount').textContent=`${s.uploads.length}/20 documents`;
  $('quota').textContent=`${s.runs_remaining} of ${s.run_quota} runs remaining`;
  $('runbtn').disabled=s.runs_remaining<1||s.uploads.length<1;
  $('docs').innerHTML=s.uploads.map(u=>
    `<div class="doc"><span class="sid">${u.source_id}</span>`+
    `<span>${u.filename}</span>`+
    `<span class="meta">${u.approved?'attested approved':'DRAFT, not citable'}</span></div>`).join('')
    ||'<div class="quota">No documents yet. Upload evidence or seed the sample pack.</div>';
  $('runs').innerHTML=s.runs.map(r=>{
    let links='';
    if(r.status==='done'){
      links=`<a class="filelink" target="_blank" href="/t/${slug}/runs/${r.id}/run_report.html">report</a>
      <a class="filelink" href="/t/${slug}/runs/${r.id}/${r.id}__DELIVERED.xlsx">DELIVERED.xlsx</a>
      <a class="filelink" target="_blank" href="/t/${slug}/runs/${r.id}/audit_log.jsonl">audit chain</a>`;
    }
    return `<div class="runrow"><span>${r.id}</span><span class="chip ${
      r.status==='done'?'c-ok':r.status==='error'?'c-warn':'c-sig'}">${r.status}</span>${links}
      ${r.error?`<span class="err" style="margin:0">${r.error}</span>`:''}</div>`;
  }).join('');
}
$('upform').onsubmit=async e=>{
  e.preventDefault();$('uperr').textContent='';$('upok').textContent='';$('upbtn').disabled=true;
  const fd=new FormData($('upform'));
  const r=await fetch(`/t/${slug}/api/upload`,{method:'POST',body:fd});
  const data=await r.json();
  if(data.error){$('uperr').textContent=data.error;}
  else{$('upok').textContent=`Ingested as ${data.source_id}`;$('upform').reset();}
  $('upbtn').disabled=false;refresh();
};
$('seedbtn').onclick=async()=>{
  $('uperr').textContent='';
  const r=await fetch(`/t/${slug}/api/seed`,{method:'POST'});
  const data=await r.json();
  if(data.error)$('uperr').textContent=data.error;
  else $('upok').textContent=`Seeded ${data.count} sample documents`;
  refresh();
};
let pollTimer=null;
async function poll(runId){
  const r=await (await fetch(`/t/${slug}/api/run/${runId}`)).json();
  if(r.status==='queued'){$('runstat').innerHTML=`<span class="quota">Queued, position ${r.position}. Runs take about two minutes.</span><progress></progress>`;}
  else if(r.status==='running'){$('runstat').innerHTML=`<span class="quota">Running: drafting and gating ten questions. About two minutes.</span><progress></progress>`;}
  else{
    $('runstat').innerHTML='';clearInterval(pollTimer);pollTimer=null;refresh();
    if(r.status==='done'){window.open(`/t/${slug}/runs/${runId}/run_report.html`,'_blank');}
    if(r.error)$('runerr').textContent=r.error;
  }
}
$('runbtn').onclick=async()=>{
  $('runerr').textContent='';$('runbtn').disabled=true;
  const r=await fetch(`/t/${slug}/api/run`,{method:'POST'});
  const data=await r.json();
  if(data.error){$('runerr').textContent=data.error;$('runbtn').disabled=false;return;}
  pollTimer=setInterval(()=>poll(data.run_id),2000);poll(data.run_id);
};
refresh();
</script>"""
    return _page(f"TrustOps, {org}", body + js)


def review_page(slug: str, org: str, runs: list[dict]) -> str:
    runs_json = json.dumps(runs)
    body = f"""
<header>
<div class="eyebrow"><b>TrustOps</b> / review queue / {_html.escape(slug)}</div>
<h1>Named review</h1>
<div class="runmeta">Approving releases a cited draft into the DELIVERED workbook. Rejecting sends
it back to the exception queue. Every action writes your name and note into the tamper-evident
audit chain. Exceptions cannot be approved: an answer without a surviving citation never ships.</div>
</header>
<p class="sub" style="margin-top:20px"><a class="filelink" href="/t/{slug}">Back to workspace</a></p>
<div id="queue"></div>
<footer>TrustOps hosted demo / reviewer identity is self-attested in the demo</footer>
"""
    js = """
<script>
const slug=location.pathname.split('/')[2];
const RUNS=__RUNS__;
const $=id=>document.getElementById(id);
function render(){
  $('queue').innerHTML=RUNS.map(run=>{
    const items=run.items.map(it=>{
      const cited=it.state==='GRC_REVIEW';
      return `<div class="qcard" id="card-${run.id}-${it.question_id}">
      <div class="row" style="margin:0;justify-content:space-between">
        <span class="chip ${cited?'c-rev':'c-warn'}">${cited?'CITED, AWAITING REVIEW':'EXCEPTION, '+(it.route||'SME')}</span>
        <span class="quota">${it.question_id} / ${it.domain}</span></div>
      <h3>${it.text}</h3>
      ${it.answer?`<div class="body">${it.answer}</div>`:'<div class="body"><em>No answer released.</em></div>'}
      ${it.citations.length?`<div class="prov">${it.citations.join('<br>')}</div>`:''}
      ${it.gaps.map(g=>`<div class="gap">&#9656; ${g}</div>`).join('')}
      <div class="grid2" style="margin-top:12px">
        <div><label>Your name</label><input type="text" id="rev-${run.id}-${it.question_id}" placeholder="Full name"></div>
        <div><label>Note (required)</label><input type="text" id="note-${run.id}-${it.question_id}" placeholder="Why this decision"></div>
      </div>
      <div class="row">
        ${cited?`<button class="primary" onclick="act('${run.id}','${it.question_id}','approve')">Approve and release</button>
        <button onclick="act('${run.id}','${it.question_id}','reject')">Reject</button>`
        :`<button onclick="act('${run.id}','${it.question_id}','route')">Add routing note</button>`}
      </div>
      <div class="err" id="err-${run.id}-${it.question_id}"></div></div>`;
    }).join('');
    return `<div class="seclabel"><span class="idx">${run.id}</span><span class="label">${run.items.length} awaiting</span><span class="rule"></span></div>${items||'<p class="sub">Nothing awaiting review in this run.</p>'}`;
  }).join('')||'<p class="sub">No completed runs yet. Run the questionnaire from the workspace first.</p>';
}
async function act(runId,qid,action){
  const rev=$(`rev-${runId}-${qid}`).value,note=$(`note-${runId}-${qid}`).value;
  const el=$(`err-${runId}-${qid}`);el.textContent='';
  const r=await fetch(`/t/${slug}/api/review`,{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({run_id:runId,question_id:qid,action,reviewer:rev,note})});
  const data=await r.json();
  if(data.error){el.textContent=data.error;return;}
  const run=RUNS.find(x=>x.id===runId);
  run.items=run.items.filter(x=>x.question_id!==qid||action==='route');
  render();
}
render();
</script>"""
    return _page(f"TrustOps review, {org}", body + js.replace("__RUNS__", runs_json))
