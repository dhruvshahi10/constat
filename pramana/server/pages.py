"""Hosted HTML pages: workspace and review queue, on the brand system.

Same pattern as ui/app.py: Python string templates + inline JS, zero build
step, brand.stylesheet() inlined so pages make no external requests.

Two rules this file has to keep, because it renders attacker-controlled text:

  * every value interpolated into innerHTML goes through the client-side
    esc() helper. Filenames, document titles and extracted document text are
    all uploader-controlled, and a workspace link is shareable.
  * JSON inlined into a <script> has "<" escaped to \\u003c, because
    json.dumps does not escape "</script>".
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
input:focus-visible,select:focus-visible,textarea:focus-visible,button:focus-visible,
a:focus-visible,summary:focus-visible,[tabindex]:focus-visible{
outline:2px solid var(--focus-ring);outline-offset:2px;border-radius:var(--radius-1)}
label{display:block;font-family:var(--font-mono);font-size:10px;letter-spacing:0.13em;
text-transform:uppercase;color:var(--text-tertiary);margin:14px 0 6px}
select,button{font-family:var(--font-mono);font-size:11px;letter-spacing:0.1em;text-transform:uppercase;
padding:10px 15px;border:1px solid var(--line-2);border-radius:var(--radius-1);
background:var(--surface-raised);color:var(--text-primary);cursor:pointer}
button.primary{background:var(--signal);color:var(--signal-ink);border-color:var(--signal)}
button.primary:hover{background:var(--signal-bright)}
button:disabled{opacity:.55;cursor:not-allowed}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:14px}
.grid2{display:grid;gap:0 18px;grid-template-columns:1fr 1fr}
@media(max-width:640px){.grid2{grid-template-columns:1fr}}
.doc{display:flex;gap:12px;align-items:baseline;padding:10px 0;border-bottom:1px solid var(--line-1);
font-size:13.5px;flex-wrap:wrap}
.doc:last-child{border-bottom:0}
.doc .sid{font-family:var(--font-mono);font-size:11px;color:var(--signal)}
.doc .meta{font-family:var(--font-mono);font-size:10.5px;color:var(--text-tertiary)}
.doc .fname{word-break:break-word;min-width:0}
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
/* the exception chip carries a routing address list, which can be longer than
   a phone is wide; .chip is nowrap by default, so opt this one out */
.qcard .chip{white-space:normal;word-break:break-word;max-width:100%;text-align:left;
align-items:flex-start}
.qcard .chip::before{margin-top:5px}
.qcard .body{font-size:14px;color:var(--text-primary);background:var(--surface-sunken);
border-radius:var(--radius-1);padding:12px 14px;margin:10px 0}
.gap{color:var(--status-warn);font-family:var(--font-mono);font-size:11.5px;line-height:1.7}
.prov{font-family:var(--font-mono);font-size:10.5px;color:var(--text-tertiary);
border-left:2px solid var(--status-ok);padding-left:9px;margin-top:8px}
textarea{width:100%;min-height:52px;font-family:var(--font-sans);font-size:13.5px;
color:var(--text-primary);background:var(--surface-sunken);border:1px solid var(--line-1);
border-radius:var(--radius-1);padding:10px 12px;resize:vertical}
.quota{font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary)}
progress{width:100%;height:6px;accent-color:var(--signal);margin-top:8px}

/* workspace address, shown so the only key to this workspace is recoverable */
.wsaddr{margin-top:18px;background:var(--surface-card);border:1px solid var(--line-signal);
border-radius:var(--radius-2);padding:14px 16px}
.wsaddr .lbl{font-family:var(--font-mono);font-size:10px;letter-spacing:0.13em;
text-transform:uppercase;color:var(--text-tertiary);margin-bottom:7px}
.wsaddr .addr{font-family:var(--font-mono);font-size:12px;color:var(--signal);word-break:break-all;
line-height:1.7}
.wsaddr p{font-family:var(--font-mono);font-size:11px;color:var(--status-warn);margin-top:8px;
line-height:1.7}

/* per-file upload rows */
.fdrop{margin-left:auto;font-family:var(--font-mono);font-size:10px;letter-spacing:0.1em;
text-transform:uppercase;padding:4px 9px;border:1px solid var(--line-2);border-radius:var(--radius-1);
background:transparent;color:var(--text-tertiary);cursor:pointer}
.fdrop:hover{color:var(--status-critical);border-color:var(--status-critical)}
.fn{display:flex;align-items:center;gap:10px}
.frow{border:1px solid var(--line-1);border-radius:var(--radius-2);padding:12px 14px;margin-top:12px;
background:var(--surface-sunken)}
.frow .fn{font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary);word-break:break-all;
display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}
.frow .fn b{color:var(--text-primary);font-weight:400}
.frow label{margin-top:10px}
.frow input,.frow select{background:var(--surface-card)}
.frow .st{font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.08em}
.frow .st.ok{color:var(--status-ok)}
.frow .st.bad{color:var(--status-critical)}
details.more{margin-top:12px}
details.more>summary{font-family:var(--font-mono);font-size:10px;letter-spacing:0.13em;
text-transform:uppercase;color:var(--text-tertiary);cursor:pointer;list-style:none;
display:inline-flex;gap:7px;align-items:center;padding:4px 0}
details.more>summary::-webkit-details-marker{display:none}
details.more>summary::before{content:"+";color:var(--signal);font-size:12px}
details.more[open]>summary::before{content:"\\2212"}
.attest{display:flex;gap:10px;align-items:flex-start;margin:18px 0 0;padding:13px 15px;
background:var(--status-warn-wash);border:1px solid var(--line-1);
border-left:2px solid var(--status-warn);border-radius:var(--radius-2);
font-family:var(--font-sans);font-size:12.5px;text-transform:none;letter-spacing:0;
color:var(--text-primary)}
.attest input{width:auto;flex:0 0 auto;margin-top:3px}
.attest span{font-size:12.5px;color:var(--text-primary);line-height:1.6}
.attest em{display:block;font-style:normal;font-family:var(--font-mono);font-size:10.5px;
color:var(--text-tertiary);margin-top:5px;letter-spacing:0.04em}

/* run status + result card */
.blockreason{font-family:var(--font-mono);font-size:11px;color:var(--status-warn);line-height:1.7}
.runline{font-family:var(--font-mono);font-size:12px;color:var(--text-secondary);line-height:1.8}
.runline b{color:var(--text-primary);font-weight:400}
.result{background:var(--surface-card);border:1px solid var(--line-signal);
border-left:2px solid var(--status-ok);border-radius:var(--radius-2);padding:20px 22px;margin-top:14px}
.result:focus{outline:2px solid var(--focus-ring);outline-offset:2px}
.result h3{font-family:var(--font-display);font-size:21px;margin:12px 0 6px}
.result .tally{font-family:var(--font-mono);font-size:11.5px;color:var(--text-tertiary);line-height:1.9}
.result .acts{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;align-items:center}
a.abtn{font-family:var(--font-mono);font-size:11px;letter-spacing:0.1em;text-transform:uppercase;
padding:12px 18px;border-radius:var(--radius-1);text-decoration:none;display:inline-block}
a.abtn-primary{background:var(--signal);color:var(--signal-ink)}
a.abtn-primary:hover{background:var(--signal-bright)}
a.abtn-ghost{border:1px solid var(--line-2);color:var(--text-primary)}
a.abtn-ghost:hover{border-color:var(--line-signal)}

.tiers{display:grid;gap:1px;background:var(--line-1);border:1px solid var(--line-1);
border-radius:var(--radius-2);overflow:hidden;grid-template-columns:1fr;margin-top:18px}
@media(min-width:820px){.tiers{grid-template-columns:1fr 1fr 1fr}}
.tier{background:var(--surface-card);padding:18px 20px}
.tier h3{font-size:16px;margin:9px 0 7px}
.tier p{font-size:13px;line-height:1.6;color:var(--text-secondary)}
"""


FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Cpath d='M16 3 27 7v9c0 7-4.6 11.4-11 13C9.6 27.4 5 23 5 16V7z' fill='none' "
    "stroke='%23B7C4FF' stroke-width='2.4'/%3E%3Cpath d='M11 16.5 14.5 20 21 12' fill='none' "
    "stroke='%23B7C4FF' stroke-width='2.4'/%3E%3C/svg%3E"
)


def _page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex">'
            f'<link rel="icon" href="{FAVICON}">'
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


def _inline_json(obj) -> str:
    """json.dumps does not escape '</script>'. This does."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


# Shared by workspace and landing: a client-side HTML escaper. Everything that
# reaches innerHTML in these pages passes through it.
ESC_JS = """
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
"""


def workspace(slug: str, org: str) -> str:
    body = f"""
<header>
<div class="eyebrow"><b>Pramana</b> / workspace / {_html.escape(slug)}</div>
<h1>{_html.escape(org)}</h1>
<div class="runmeta">Evidence stays in this workspace. Retrieval runs on our server;
only a question and its retrieved excerpts ever reach the drafting model.
This workspace and everything in it is deleted 14 days after signup.</div>
<div class="wsaddr">
  <div class="lbl">Your workspace address</div>
  <div class="addr" id="wsaddr">&#8230;</div>
  <p>Bookmark this. It is the only key to this workspace. There is no password
  reset and we do not email it to you.</p>
</div>
</header>

<div class="seclabel"><span class="idx">01</span><span class="label">Evidence</span><span class="rule"></span></div>
<h2>Upload public evidence</h2>
<p class="sub">This demo drafts with Google Gemini on its free tier, whose terms allow Google to
use submitted content to improve their services. So upload documents you are happy to have public:
a published SOC 2 report, an ISO certificate, trust-center policies. Do not upload confidential
evidence here. PDF, DOCX, MD or TXT, up to 5MB each, 20 per workspace. Answers can only cite
documents you attest are approved and current.</p>
<div class="console">
<form id="upform">
<label for="file">Files</label>
<input type="file" id="file" name="file" accept=".pdf,.docx,.md,.txt" multiple required>
<p class="quota" style="margin-top:8px">Pick several at once. Title, type and version are guessed
from each filename; correct anything that is wrong.</p>

<div id="filerows"></div>

<div class="grid2" style="margin-top:8px">
<div><label for="owner">Owner email</label>
  <input type="email" id="owner" name="owner" required placeholder="security@yourco.com"></div>
<div><label for="effective_date">Effective date</label>
  <input type="date" id="effective_date" name="effective_date" required></div>
<div><label for="expiry_date">Expiry date</label>
  <input type="date" id="expiry_date" name="expiry_date" required></div>
</div>
<p class="quota" style="margin-top:8px">Owner and dates apply to every file in this batch and stay
filled in for the next one.</p>

<label class="attest" for="attested">
  <input type="checkbox" id="attested" name="attested" required>
  <span>I attest these documents are approved and current in my organization.
  <em>Required. An unattested document is stored as a draft, and the gates refuse to cite drafts,
  so a run over unattested evidence refuses every question.</em></span>
</label>

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
<div class="blockreason" id="runblock" style="margin-top:10px"></div>
<div id="runstat" style="margin-top:14px"></div>
<div id="runlive" aria-live="polite" aria-atomic="true"></div>
<div class="err" id="runerr"></div>
<div id="runs" style="margin-top:10px"></div>
</div>

<div class="seclabel"><span class="idx">03</span><span class="label">Review</span><span class="rule"></span></div>
<h2>Named review before anything ships</h2>
<p class="sub">Nothing reaches DELIVERED without a named reviewer and a note in the audit chain.
<a class="filelink" href="/t/{slug}/review">Open the review queue</a></p>

<div class="seclabel"><span class="idx">04</span><span class="label">Which key drafts</span><span class="rule"></span></div>
<h2>Three tiers, one honest difference</h2>
<p class="sub">The gates, the audit chain and the deliverables are identical in all three. What
changes is whose API key drafts your answers, and therefore whose terms your text is under.</p>
<div class="tiers">
  <div class="tier"><span class="chip c-sig">DEMO, THIS WORKSPACE</span>
    <h3>Our key</h3>
    <p>Google Gemini on the free tier. Google may use submitted content to improve their services.
    Public evidence only. Three runs, then the workspace is deleted after 14 days.</p></div>
  <div class="tier"><span class="chip c-ok">BYOK</span>
    <h3>Your key</h3>
    <p>You supply a provider key. Your text is under your contract with that provider, not ours,
    which is the tier for confidential evidence.</p></div>
  <div class="tier"><span class="chip c-rev">MANAGED</span>
    <h3>Paid, with commitments</h3>
    <p>We run the key on a paid tier that carries a no-training commitment, and we pass that
    commitment through to you in writing.</p></div>
</div>
<p class="sub" style="margin-top:16px">BYOK and Managed are not built yet. Say which one you need
and it moves up the queue.
<a class="filelink" href="https://www.linkedin.com/in/dhruvshahi-/" target="_blank" rel="noopener">Tell me on LinkedIn</a></p>

<footer>Pramana hosted demo / public evidence only on this tier / data deleted after 14 days /
<a class="filelink" href="/site/legal/terms.html">Terms</a> /
<a class="filelink" href="/site/legal/privacy.html">Privacy and data handling</a> /
<a class="filelink" href="https://www.linkedin.com/in/dhruvshahi-/" target="_blank" rel="noopener">talk about a pilot</a></footer>
"""
    js = """
<script>
const slug=location.pathname.split('/')[2];
const $=id=>document.getElementById(id);
__ESC__
const RUNKEY='pramana_run_'+slug;
const QLIST=__QLIST__;

/* ---- workspace address, always visible and always copyable --------------- */
$('wsaddr').textContent=location.origin+location.pathname;

/* ---- upload: many files, guessed metadata, sticky batch fields ----------- */
const TYPE_HINTS=[
  [/\\bsoc\\s*-?2|\\bsoc2\\b/i,'attestation'],
  [/\\biso\\b|\\b27001\\b|\\bcert(ificate)?\\b/i,'certificate'],
  [/\\bpen[\\s_-]?test|\\bpentest|\\bpenetration\\b/i,'report'],
  [/\\breport\\b|\\baudit\\b/i,'report'],
  [/\\bpolicy\\b|\\bpolicies\\b/i,'policy'],
  [/\\bstandard\\b|\\bbaseline\\b/i,'standard'],
  [/\\bplan\\b|\\bprocedure\\b|\\brunbook\\b/i,'plan'],
  [/\\broadmap\\b/i,'roadmap'],
  [/\\bregister\\b|\\binventory\\b|\\blist\\b/i,'register']
];
const TITLE_SKIP=new Set(['a','an','and','as','at','by','for','in','of','on','or','the','to','v','vs']);
function guessTitle(name){
  const stem=name.replace(/\\.[^.]+$/,'').replace(/[_\\-]+/g,' ')
    .replace(/\\bv?\\d+\\.\\d+\\b/gi,' ').replace(/\\s+/g,' ').trim();
  const t=stem.split(' ').filter(Boolean).map((w,i)=>
    (i>0&&TITLE_SKIP.has(w.toLowerCase()))?w.toLowerCase()
      :w.charAt(0).toUpperCase()+w.slice(1)).join(' ');
  return (t||'Untitled document').slice(0,120);
}
function guessType(name){
  for(const [re,t] of TYPE_HINTS){if(re.test(name))return t}
  return 'policy';
}
function guessVersion(name){
  const m=name.match(/v?(\\d+\\.\\d+)/i);
  return m?m[1]:'1.0';
}
function iso(d){return d.toISOString().slice(0,10)}

let picked=[];
const edits={};   /* per-file user edits, keyed by file name */   /* the batch, source of truth for the rows below */

function rowsHTML(){
  return picked.map((f,i)=>`<div class="frow" id="frow-${i}">
    <div class="fn"><b>${esc(f.name)}</b><span class="st" id="fst-${i}"></span>
      <button type="button" class="fdrop" data-drop="${i}"
        aria-label="Remove ${esc(f.name)} from this batch">Remove</button></div>
    <div class="grid2">
      <div><label for="ftitle-${i}">Title</label>
        <input type="text" id="ftitle-${i}" maxlength="120" required value="${esc(guessTitle(f.name))}"></div>
      <div><label for="ftype-${i}">Type</label>
        <select id="ftype-${i}">__TYPES__</select></div>
    </div>
    <details class="more"><summary>Details (optional)</summary>
      <div class="grid2">
        <div><label for="fver-${i}">Version</label>
          <input type="text" id="fver-${i}" value="${esc(guessVersion(f.name))}"></div>
        <div><label for="ftop-${i}">Topics (comma separated, improves retrieval)</label>
          <input type="text" id="ftop-${i}" placeholder="encryption, key management"></div>
      </div>
    </details>
  </div>`).join('');
}
function readRows(){
  /* capture what the user typed before any re-render, keyed by file name so an
     edit survives a rejected batch. Rebuilding rows from guessTitle() threw
     away every hand-corrected title the moment one bad date failed the batch. */
  picked.forEach((f,i)=>{
    const t=$('ftitle-'+i), ty=$('ftype-'+i), v=$('fver-'+i), tp=$('ftop-'+i);
    edits[f.name]=Object.assign(edits[f.name]||{}, {
      title:t?t.value:undefined, type:ty?ty.value:undefined,
      version:v?v.value:undefined, topics:tp?tp.value:undefined});
  });
}
function renderRows(){
  $('filerows').innerHTML=rowsHTML();
  picked.forEach((f,i)=>{
    const e=edits[f.name]||{};
    const ty=$('ftype-'+i); if(ty) ty.value=e.type||guessType(f.name);
    const t=$('ftitle-'+i); if(t&&e.title!==undefined&&e.title!=='') t.value=e.title;
    const v=$('fver-'+i); if(v&&e.version) v.value=e.version;
    const tp=$('ftop-'+i); if(tp&&e.topics) tp.value=e.topics;
  });
  $('upbtn').disabled=picked.length===0;
}
function dropFile(i){
  readRows();
  picked.splice(i,1);
  renderRows();syncInput();
}
function syncInput(){
  /* keep the file control's own display in step with `picked` */
  const dt=new DataTransfer();picked.forEach(f=>dt.items.add(f));
  $('file').files=dt.files;
}
$('file').onchange=()=>{picked=Array.from($('file').files||[]);renderRows()};
/* dropping one file from a batch used to mean reopening the OS picker and
   re-selecting everything */
$('filerows').addEventListener('click',ev=>{
  const b=ev.target.closest('[data-drop]');
  if(b) dropFile(parseInt(b.dataset.drop,10));
});

/* dates default to today and today + one year: the server needs both, and
   expiry strictly after effective, so guessing badly is worse than guessing
   usefully */
(function seedDates(){
  const now=new Date();
  const yr=new Date(now.getFullYear()+1,now.getMonth(),now.getDate());
  $('effective_date').value=iso(now);$('expiry_date').value=iso(yr);
})();

$('upform').onsubmit=async e=>{
  e.preventDefault();
  $('uperr').textContent='';$('upok').textContent='';
  if(!picked.length){$('uperr').textContent='Choose at least one file.';return}
  readRows();
  $('upbtn').disabled=true;$('upbtn').textContent='Uploading';
  const failed=[],ids=[];
  for(let i=0;i<picked.length;i++){
    const st=$('fst-'+i);if(st){st.className='st';st.textContent='uploading'}
    const fd=new FormData();
    fd.append('file',picked[i]);
    fd.append('title',$('ftitle-'+i).value.trim());
    fd.append('type',$('ftype-'+i).value);
    fd.append('version',$('fver-'+i).value.trim());
    fd.append('topics',$('ftop-'+i).value.trim());
    fd.append('owner',$('owner').value.trim());
    fd.append('effective_date',$('effective_date').value);
    fd.append('expiry_date',$('expiry_date').value);
    if($('attested').checked)fd.append('attested','on');
    let data;
    try{
      const r=await fetch(`/t/${slug}/api/upload`,{method:'POST',body:fd});
      data=await r.json();
    }catch(err){data={error:'Network error during upload.'}}
    if(data.error){
      failed.push({file:picked[i],msg:data.error,i});
      if(st){st.className='st bad';st.textContent='rejected'}
    }else{
      ids.push(data.source_id);
      if(st){st.className='st ok';st.textContent='ingested '+data.source_id}
    }
  }
  if(ids.length)$('upok').textContent=`Ingested ${ids.length} document${ids.length>1?'s':''}: `+ids.join(', ');
  if(failed.length){
    $('uperr').textContent=failed.map(f=>`${f.file.name}: ${f.msg}`).join('\\n');
    /* a rejected file stays selected so the fix is one edit, not a re-pick */
    picked=failed.map(f=>f.file);renderRows();syncInput();
    /* edits were captured in readRows() before the submit, so the rebuilt
       rows come back with the user's titles and types intact */
  }else{
    /* targeted clear: files and their titles only. Owner, dates and the
       attestation stay, because they repeat across a batch. */
    picked=[];$('file').value='';renderRows();
  }
  $('upbtn').disabled=picked.length===0;$('upbtn').textContent='Upload';
  refresh();
};
$('seedbtn').onclick=async()=>{
  $('uperr').textContent='';$('seedbtn').disabled=true;
  try{
    const r=await fetch(`/t/${slug}/api/seed`,{method:'POST'});
    const data=await r.json();
    if(data.error)$('uperr').textContent=data.error;
    else $('upok').textContent=`Seeded ${data.count} sample documents`;
  }catch(err){$('uperr').textContent='Network error while seeding.'}
  $('seedbtn').disabled=false;refresh();
};

/* ---- state ---------------------------------------------------------------- */
let attestedCount=0,runsRemaining=0;
function setRunGate(){
  const reasons=[];
  if(attestedCount<1)reasons.push('No attested documents yet. Nothing can be cited.');
  if(runsRemaining<1)reasons.push('No runs left in this workspace.');
  $('runbtn').disabled=reasons.length>0||pollingId!==null;
  $('runblock').textContent=reasons.join(' ');
}
async function refresh(){
  let s;
  try{s=await (await fetch(`/t/${slug}/api/state`)).json()}catch(err){return}
  if(s.error)return;
  attestedCount=s.uploads.filter(u=>u.approved).length;
  runsRemaining=s.runs_remaining;
  $('doccount').textContent=`${s.uploads.length}/20 documents, ${attestedCount} attested`;
  $('quota').textContent=`${s.runs_remaining} of ${s.run_quota} runs remaining`;
  /* the signup email is the sensible default owner; the server may or may not
     send it, so this is opportunistic, never required */
  const seedOwner=s.email||s.signup_email||'';
  if(seedOwner&&!$('owner').value)$('owner').value=seedOwner;
  $('docs').innerHTML=s.uploads.map(u=>
    `<div class="doc"><span class="sid">${esc(u.source_id)}</span>`+
    `<span class="fname">${esc(u.filename)}</span>`+
    (u.approved?`<span class="chip c-ok">ATTESTED APPROVED</span>`
               :`<span class="chip c-warn">DRAFT, NOT CITABLE</span>`)+
    `</div>`).join('')
    ||'<div class="quota">No documents yet. Upload public evidence or seed the sample pack.</div>';
  $('runs').innerHTML=s.runs.map(r=>{
    let links='';
    if(r.status==='done'){
      const id=encodeURIComponent(r.id);
      links=`<a class="filelink" target="_blank" rel="noopener" href="/t/${slug}/runs/${id}/run_report.html">report</a>
      <a class="filelink" href="/t/${slug}/runs/${id}/${id}__DELIVERED.xlsx">DELIVERED.xlsx</a>
      <a class="filelink" target="_blank" rel="noopener" href="/t/${slug}/runs/${id}/audit_log.jsonl">audit chain</a>`;
    }
    return `<div class="runrow"><span>${esc(r.id)}</span><span class="chip ${
      r.status==='done'?'c-ok':r.status==='error'?'c-warn':'c-sig'}">${esc(r.status)}</span>${links}
      ${r.error?`<span class="err" style="margin:0">${esc(r.error)}</span>`:''}</div>`;
  }).join('');
  /* a reload mid-run used to leave a frozen page: no timer existed outside the
     click handler. Resume from whatever the server says is in flight. */
  const live=s.runs.find(r=>r.status==='queued'||r.status==='running');
  if(live)startPoll(live.id);
  else if(pollingId&&!s.runs.some(r=>r.id===pollingId&&(r.status==='queued'||r.status==='running')))stopPoll();
  setRunGate();
}

/* ---- run polling and the result card ------------------------------------- */
let pollTimer=null,pollingId=null;
function stopPoll(){if(pollTimer)clearInterval(pollTimer);pollTimer=null;pollingId=null}
function startPoll(runId){
  if(pollingId===runId)return;
  stopPoll();pollingId=runId;
  try{sessionStorage.setItem(RUNKEY,runId)}catch(e){}
  pollTimer=setInterval(()=>poll(runId),2000);poll(runId);
}
function progressHTML(r,label){
  const cur=Number(r.current_q),tot=Number(r.total_q);
  if(Number.isFinite(cur)&&Number.isFinite(tot)&&tot>0&&cur>0){
    /* two minutes of an indeterminate bar and one static sentence is dead
       time. Name the question the engine is on. */
    const t=QLIST[cur-1];
    const q=t?`<div class="runline">Now gating: ${esc(t)}</div>`:'';
    return `<div class="runline"><b>${label}</b> Question ${cur} of ${tot}.</div>
      <progress aria-label="Run progress, question ${cur} of ${tot}" value="${cur}" max="${tot}"></progress>${q}`;
  }
  return `<div class="runline"><b>${label}</b></div>
    <progress aria-label="Run in progress, time remaining unknown"></progress>`;
}
function resultCard(runId,m){
  const id=encodeURIComponent(runId);
  const total=Number(m&&m.questions)||10;
  const delivered=Number(m&&m.auto_approved_delivered)||0;
  const refused=Number(m&&m.exception_queue)||0;
  const awaiting=Number(m&&m.awaiting_human_review)||0;
  const extra=awaiting?`<div class="tally">${awaiting} cited and waiting for a named reviewer.</div>`:'';
  return `<div class="result" id="resultcard" tabindex="-1">
    <span class="chip c-ok">RUN COMPLETE</span>
    <h3>Run complete. ${total} questions, ${delivered} delivered, ${refused} refused.</h3>
    ${extra}
    <div class="tally">Every refusal names its gap in the report.</div>
    <div class="acts">
      <a class="abtn abtn-primary" target="_blank" rel="noopener"
         href="/t/${slug}/runs/${id}/run_report.html">View the run report</a>
      <a class="abtn abtn-ghost" href="/t/${slug}/runs/${id}/${id}__DELIVERED.xlsx">Download DELIVERED.xlsx</a>
      <a class="abtn abtn-ghost" href="/t/${slug}/review">Open the review queue</a>
    </div>
  </div>`;
}
async function poll(runId){
  let r;
  try{r=await (await fetch(`/t/${slug}/api/run/${runId}`)).json()}catch(err){return}
  if(r.error&&!r.status){stopPoll();$('runerr').textContent=r.error;return}
  if(r.status==='queued'){
    $('runstat').innerHTML=progressHTML(r,`Queued, position ${Number(r.position)||0}. Runs take about two minutes.`);
  }else if(r.status==='running'){
    $('runstat').innerHTML=progressHTML(r,'Running: drafting and gating ten questions.');
  }else{
    stopPoll();
    try{sessionStorage.removeItem(RUNKEY)}catch(e){}
    if(r.status==='done'){
      /* never window.open here. Two minutes after the last gesture there is no
         transient activation left, so a popup blocker eats it and the user
         sees nothing at all. A real anchor carries the click's activation. */
      $('runstat').innerHTML=resultCard(runId,r.metrics);
      $('runlive').textContent=`Run complete. ${Number(r.metrics&&r.metrics.questions)||10} questions gated. The run report is ready.`;
      const card=$('resultcard');if(card)card.focus();
    }else{
      $('runstat').innerHTML='';
      $('runlive').textContent='The run stopped before it finished.';
    }
    if(r.error)$('runerr').textContent=r.error;
    refresh();
  }
}
$('runbtn').onclick=async()=>{
  $('runerr').textContent='';$('runstat').innerHTML='';$('runlive').textContent='';
  $('runbtn').disabled=true;
  let data;
  try{
    const r=await fetch(`/t/${slug}/api/run`,{method:'POST'});
    data=await r.json();
  }catch(err){data={error:'Network error starting the run.'}}
  if(data.error){$('runerr').textContent=data.error;setRunGate();return}
  startPoll(data.run_id);
};

/* resume a run this tab started, before the first refresh() lands */
try{const saved=sessionStorage.getItem(RUNKEY);if(saved)startPoll(saved)}catch(e){}
renderRows();
refresh();
</script>"""
    js = (js.replace("__ESC__", ESC_JS)
            .replace("__TYPES__", TYPE_OPTIONS)
            .replace("__QLIST__", _inline_json([t for _q, _d, t in DEMO_QUESTIONS])))
    return _page(f"Pramana, {org}", body + js)


def review_page(slug: str, org: str, runs: list[dict]) -> str:
    runs_json = _inline_json(runs)
    body = f"""
<header>
<div class="eyebrow"><b>Pramana</b> / review queue / {_html.escape(slug)}</div>
<h1>Named review</h1>
<div class="runmeta">Approving releases a cited draft into the DELIVERED workbook. Rejecting sends
it back to the exception queue. Every action writes your name and note into the tamper-evident
audit chain. Exceptions cannot be approved: an answer without a surviving citation never ships.</div>
</header>
<p class="sub" style="margin-top:20px"><a class="filelink" href="/t/{slug}">Back to workspace</a></p>
<div id="queue"></div>
<footer>Pramana hosted demo / reviewer identity is self-attested in the demo /
<a class="filelink" href="/site/legal/terms.html">Terms</a> /
<a class="filelink" href="/site/legal/privacy.html">Privacy and data handling</a></footer>
"""
    js = """
<script>
const slug=location.pathname.split('/')[2];
const RUNS=__RUNS__;
const $=id=>document.getElementById(id);
__ESC__
function render(){
  $('queue').innerHTML=RUNS.map(run=>{
    const rid=esc(run.id);
    const items=run.items.map(it=>{
      const cited=it.state==='GRC_REVIEW';
      const qid=esc(it.question_id);
      return `<div class="qcard" id="card-${rid}-${qid}">
      <div class="row" style="margin:0;justify-content:space-between">
        <span class="chip ${cited?'c-rev':'c-warn'}">${cited?'CITED, AWAITING REVIEW':'EXCEPTION, '+esc(it.route||'SME')}</span>
        <span class="quota">${qid} / ${esc(it.domain)}</span></div>
      <h3>${esc(it.text)}</h3>
      ${it.answer?`<div class="body">${esc(it.answer)}</div>`:'<div class="body"><em>No answer released.</em></div>'}
      ${it.citations.length?`<div class="prov">${it.citations.map(esc).join('<br>')}</div>`:''}
      ${it.gaps.map(g=>`<div class="gap">&#9656; ${esc(g)}</div>`).join('')}
      <div class="grid2" style="margin-top:12px">
        <div><label for="rev-${rid}-${qid}">Your name</label>
          <input type="text" id="rev-${rid}-${qid}" placeholder="Full name"></div>
        <div><label for="note-${rid}-${qid}">Note (required)</label>
          <input type="text" id="note-${rid}-${qid}" placeholder="Why this decision"></div>
      </div>
      <div class="row">
        ${cited?`<button class="primary" data-run="${rid}" data-q="${qid}" data-act="approve">Approve and release</button>
        <button data-run="${rid}" data-q="${qid}" data-act="reject">Reject</button>`
        :`<button data-run="${rid}" data-q="${qid}" data-act="route">Add routing note</button>`}
      </div>
      <div class="err" id="err-${rid}-${qid}"></div></div>`;
    }).join('');
    return `<div class="seclabel"><span class="idx">${rid}</span><span class="label">${run.items.length} awaiting</span><span class="rule"></span></div>${items||'<p class="sub">Nothing awaiting review in this run.</p>'}`;
  }).join('')||'<p class="sub">No completed runs yet. Run the questionnaire from the workspace first.</p>';
}
/* delegation, not inline onclick: question ids come from an uploaded workbook
   and have no business being spliced into an attribute */
$('queue').addEventListener('click',ev=>{
  const b=ev.target.closest('button[data-act]');
  if(b)act(b.dataset.run,b.dataset.q,b.dataset.act,b);
});
async function act(runId,qid,action,btn){
  const rev=$(`rev-${runId}-${qid}`).value,note=$(`note-${runId}-${qid}`).value;
  const el=$(`err-${runId}-${qid}`);el.textContent='';
  btn.disabled=true;
  let data;
  try{
    const r=await fetch(`/t/${slug}/api/review`,{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({run_id:runId,question_id:qid,action,reviewer:rev,note})});
    data=await r.json();
  }catch(err){data={error:'Network error. Nothing was recorded.'}}
  if(data.error){el.textContent=data.error;btn.disabled=false;return}
  const run=RUNS.find(x=>x.id===runId);
  run.items=run.items.filter(x=>x.question_id!==qid||action==='route');
  render();
}
render();
</script>"""
    js = js.replace("__ESC__", ESC_JS).replace("__RUNS__", runs_json)
    return _page(f"Pramana review, {org}", body + js)
