"""Pramana console — zero-dependency web UI over the evidence-gated engine.

  .venv/bin/python ui/app.py          # http://localhost:8787
  .venv/bin/python ui/app.py --port N

Stdlib only (http.server + urllib already used by the engine). The console is
a thin client over the same pipeline the tests exercise: every answer shown
here went through classify -> retrieve -> draft -> gates. Refusals render as
first-class outcomes, because in this product a refusal is evidence of
control, not failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trustops.drafter import make_drafter                     # noqa: E402
from trustops.envfile import load_env                         # noqa: E402
from trustops.evidence import EvidenceStore                   # noqa: E402
from trustops.gates import post_gate, pre_gate                # noqa: E402
from trustops.models import Draft, Question                   # noqa: E402
from trustops.pipeline import run                             # noqa: E402
from trustops.report import CSS, write_report                 # noqa: E402
from trustops.retrieve import Retriever                       # noqa: E402
from trustops.review import ReviewError, ReviewSession        # noqa: E402
from trustops import tenants as tn                            # noqa: E402

import os                                                     # noqa: E402

EVIDENCE = ROOT / "data" / "evidence"
QUESTIONNAIRES = ROOT / "data" / "questionnaires"
DEFAULT_QNR = QUESTIONNAIRES / "acme_security_questionnaire.xlsx"
RUNS = ROOT / "runs"


def questionnaire_for(tenant: str) -> Path:
    """A tenant's own workbook if it has one, else the shared CAIQ-style subset.

    Layout is detected per file (see `export.detect_layout`), so a client can
    drop in the buyer's actual questionnaire without any code change."""
    for pattern in (f"{tenant}_*.xlsx", f"{tenant}-*.xlsx", f"{tenant}.xlsx"):
        matches = sorted(QUESTIONNAIRES.glob(pattern))
        if matches:
            return matches[0]
    return DEFAULT_QNR


def tenant_options() -> list[dict]:
    return [{"slug": t.slug, "label": t.title,
             "sources": tn.source_count(EVIDENCE, t.slug),
             "staged": tn.staged_count(EVIDENCE, t.slug),
             "questionnaire": questionnaire_for(t.slug).name}
            for t in tn.list_tenants(EVIDENCE)]

DEMO_QUESTIONS = [
    "Is your organization ISO/IEC 27001 certified?",
    "Do you hold a current SOC 2 Type II attestation?",
    "Within how many days of contract termination is customer data deleted?",
    "Will Vendor contractually commit to unlimited liability for any breach?",
    "Is customer data encrypted at rest?",
]


def drafter_options() -> list[dict]:
    load_env(ROOT)  # pick up freshly pasted keys on every page refresh
    return [
        {"id": "mock", "label": "Offline (deterministic)", "available": True},
        {"id": "gemini", "label": "Gemini (free tier)",
         "available": bool(os.environ.get("GEMINI_API_KEY"))},
        {"id": "anthropic", "label": "Anthropic (Haiku 4.5)",
         "available": bool(os.environ.get("ANTHROPIC_API_KEY"))},
    ]


def answer_one(question_text: str, drafter_kind: str, tenant: str = "acme") -> dict:
    """Run a single ad-hoc question through the full gate path."""
    today = date.today()
    store = EvidenceStore(tenant, EVIDENCE)
    retriever = Retriever(store)
    q = Question(question_id="ADHOC", row=0, domain="Ad hoc", text=question_text.strip())

    others = tn.foreign_parties(EVIDENCE, tenant)
    d = Draft(question_id=q.question_id, answer=None)
    d = pre_gate(q, d, tenant, others)
    if not d.abstained:
        d = make_drafter(drafter_kind, retriever).draft(q, tenant)
        d = pre_gate(q, d, tenant, others)
    else:
        d.drafter, d.model_version, d.prompt_version = "gate", "n/a", "pre-gate-v1"
    d = post_gate(q, d, store, today)

    if d.route == "LEGAL":
        verdict = "ROUTED · LEGAL"
    elif d.abstained and any(f.startswith("CONTRADICTION") for f in d.gate_flags):
        verdict = "CONTRADICTION · ROUTED TO OWNERS"
    elif d.abstained:
        verdict = "ABSTAINED · ROUTED TO " + (d.route or "SME")
    elif d.requires_human:
        verdict = "CITED · AWAITING HUMAN REVIEW"
    else:
        verdict = "CITED · GATE-CLEAN"
    return {"verdict": verdict, "contract": d.to_contract()}


def run_batch(drafter_kind: str, tenant: str = "acme") -> dict:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RUNS / f"{stamp}-{tenant}-{drafter_kind}-console"
    questionnaire = questionnaire_for(tenant)
    res = run(questionnaire, tenant=tenant, evidence_root=EVIDENCE, out_dir=out,
              drafter_kind=drafter_kind, today=date.today())
    report = write_report(res, date.today())
    rel = out.relative_to(ROOT).as_posix()
    return {
        "metrics": res.metrics,
        "tenant": tenant,
        "questionnaire": questionnaire.name,
        "report": f"/{rel}/{report.name}",
        "delivered": f"/{rel}/{res.delivered_xlsx.name}",
        "audit": f"/{rel}/{res.audit_path.name}",
    }


# --- human review -----------------------------------------------------------
# The console does not re-implement any review rule. Every decision goes through
# `ReviewSession`, so the browser and the `review.py` CLI are the same process:
# same allowed-action logic, same hash chain, same HUMAN_AUTHORED labelling.

def _run_dir(name: str) -> Path:
    """Resolve a run directory name, refusing anything that is not a direct
    child of runs/. A run name arrives from a URL; it is a boundary."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ReviewError(f"'{name}' is not a run in this workspace")
    target = (RUNS / name).resolve()
    if target.parent != RUNS.resolve() or not target.is_dir():
        raise ReviewError(f"'{name}' is not a run in this workspace")
    return target


def _run_file(run_dir: Path, filename: str) -> str | None:
    path = run_dir / filename
    if not path.is_file():
        return None
    return f"/runs/{quote(run_dir.name)}/{quote(filename)}"


def _delivered_link(run_dir: Path) -> dict | None:
    matches = sorted(run_dir.glob("*__DELIVERED.xlsx"))
    if not matches:
        return None
    return {"name": matches[0].name, "file": _run_file(run_dir, matches[0].name)}


def review_runs() -> list[dict]:
    """Every reviewable run under runs/, most recently touched first."""
    out: list[dict] = []
    if not RUNS.is_dir():
        return out
    for d in sorted(RUNS.iterdir()):
        if not d.is_dir() or not (d / "manifest.json").is_file() \
                or not (d / "contracts.json").is_file():
            continue
        try:
            manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        except ValueError:
            continue                      # a half-written run is not reviewable
        decided = 0
        if (d / "review.json").is_file():
            try:
                decided = len(json.loads(
                    (d / "review.json").read_text(encoding="utf-8")).get("decisions", []))
            except ValueError:
                decided = 0
        out.append({
            "run": d.name,
            "tenant": manifest.get("tenant", ""),
            "drafter": manifest.get("drafter", ""),
            "run_date": manifest.get("run_date", ""),
            "questions": len(manifest.get("questions", [])),
            "decided": decided,
            "updated": datetime.fromtimestamp(d.stat().st_mtime).isoformat(timespec="seconds"),
        })
    out.sort(key=lambda r: r["updated"], reverse=True)
    return out


def review_queue(run: str, pending_only: bool = False) -> dict:
    session = ReviewSession(_run_dir(run))
    return {
        "run": run,
        "summary": session.summary(),
        "items": [item.to_dict() for item in session.queue(pending_only=pending_only)],
        "delivered": _delivered_link(session.run_dir),
        "report": _run_file(session.run_dir, "run_report.html"),
        "audit": _run_file(session.run_dir, "audit_log.jsonl"),
    }


def review_decide(body: dict) -> dict:
    """Record one named-human decision. Every rule — which actions this answer
    allows, whether the actor is named, whether an edit carries text — is
    enforced by ReviewSession and raised as ReviewError, never softened here."""
    run = body.get("run") or ""
    question_id = body.get("question_id") or ""
    session = ReviewSession(_run_dir(run))
    decision = session.decide(question_id, body.get("action") or "",
                              actor=(body.get("actor") or "").strip(),
                              note=(body.get("note") or "").strip(),
                              answer=body.get("answer"))
    item = next((i for i in session.queue() if i.question_id == question_id), None)
    return {"decision": asdict(decision),
            "item": item.to_dict() if item else None,
            "summary": session.summary()}


def review_export(run: str) -> dict:
    session = ReviewSession(_run_dir(run))
    target = session.export()
    return {"name": target.name,
            "file": f"/runs/{quote(session.run_dir.name)}/{quote(target.name)}",
            "summary": session.summary()}


EXTRA_CSS = """
.console{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--ok);padding:20px 22px;margin:24px 0}
textarea{width:100%;min-height:64px;font:14px/1.5 "IBM Plex Sans",system-ui,sans-serif;color:var(--ink);
background:var(--paper);border:1px solid var(--line);padding:10px 12px;resize:vertical}
select,button{font:600 12px "IBM Plex Mono",monospace;padding:9px 14px;border:1.5px solid var(--ink);
background:var(--card);color:var(--ink);cursor:pointer}
button.primary{background:var(--ink);color:var(--card)}
button:disabled{opacity:.45;cursor:not-allowed}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.chips button{border-width:1px;font-weight:400;padding:6px 10px;text-transform:none;color:var(--muted)}
.result{margin-top:18px;display:none}
.answer-box{border:1px solid var(--line);background:var(--paper);padding:14px 16px;margin-top:10px;font-size:14px}
.spin{display:none;font:12px "IBM Plex Mono",monospace;color:var(--muted)}
a.filelink{font:600 12px "IBM Plex Mono",monospace;color:var(--ok)}
.small{font:11px/1.6 "IBM Plex Mono",monospace;color:var(--muted);margin-top:8px}
.navlinks{margin-top:16px;font:600 12px "IBM Plex Mono",monospace}
.navlinks a{color:var(--ok);text-decoration:none;border-bottom:1.5px solid var(--ok);padding-bottom:2px}
"""

REVIEW_CSS = """
input[type=text]{font:14px/1.4 "IBM Plex Sans",system-ui,sans-serif;color:var(--ink);background:var(--paper);
border:1px solid var(--line);padding:9px 12px;min-width:300px;flex:1 1 300px}
label.fieldlabel{font:600 10px/1.4 "IBM Plex Mono",monospace;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);display:block;margin-bottom:6px}
label.inline{font:12px "IBM Plex Mono",monospace;color:var(--muted);display:flex;align-items:center;gap:6px}
.rev-item{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--line);
padding:16px 18px;margin-bottom:12px}
.rev-item.is-decided{border-left-color:var(--ok)}
.rev-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.rev-q{font-size:14px;margin-top:10px;max-width:78ch}
.decided{margin-top:10px;font:11px/1.6 "IBM Plex Mono",monospace;color:var(--ok);
border-left:3px solid var(--ok);padding-left:8px}
.blocked{margin-top:12px;font:11px/1.7 "IBM Plex Mono",monospace;color:var(--warn);
border-left:3px solid var(--warn);padding:4px 0 4px 8px;
background:linear-gradient(90deg,var(--warnbg),transparent 70%);max-width:80ch}
.editbox{display:none;margin-top:12px;border:1.5px solid var(--warn);background:var(--warnbg);padding:12px 14px}
.editbox.open{display:block}
.editwarn{font:700 11px/1.5 "IBM Plex Mono",monospace;letter-spacing:.1em;
text-transform:uppercase;color:var(--warn)}
.editnote{font-size:12.5px;color:var(--ink);margin:6px 0 10px;max-width:72ch}
.msg{margin-top:12px;font:12px/1.6 "IBM Plex Mono",monospace;min-height:19px}
.msg.err{color:var(--bad)} .msg.ok{color:var(--ok)}
.rev-empty{color:var(--muted);font-size:13px;padding:14px 0}
"""

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pramana console</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>/*CSS*/</style></head><body><div class="wrap">
<header>
<div class="eyebrow">Pramana · Evidence-Gated Answer Engine</div>
<h1>Every answer cited to an approved source — or refused.</h1>
<div class="runmeta" id="tenantmeta">gates: cite-or-abstain · cert-evidence-class · staleness · contradiction · legal-routing · tenant-isolation</div>
<div class="navlinks"><a href="/review">human review console &rarr;</a></div>
</header>

<h2>Ask a security question</h2>
<p class="sub">Drafts are produced by the selected model, then every citation must survive the deterministic
gates. No surviving citation &rarr; the engine refuses and names the gap. Try the planted traps below.</p>
<div class="console">
<textarea id="q" placeholder="e.g. Is customer data encrypted in transit?"></textarea>
<div class="chips" id="chips"></div>
<div class="row">
  <select id="tenant" title="Client workspace — each is a separate evidence store"></select>
  <select id="drafter"></select>
  <button class="primary" id="ask">Run through gates</button>
  <span class="spin" id="askspin">drafting &rarr; gating&hellip;</span>
</div>
<div class="result" id="askresult">
  <span class="chip" id="verdict"></span>
  <div class="answer-box" id="answer"></div>
  <div id="prov"></div>
  <div id="gaps"></div>
  <div class="small" id="meta"></div>
</div>
</div>

<h2>Run the full questionnaire</h2>
<p class="sub">Processes the selected client\'s workbook end to end: ingest &rarr; classify &rarr; draft &rarr; gates
&rarr; simulated review &rarr; export. Produces the audit working paper, the DELIVERED workbook, and the
hash-chained audit log.</p>
<div class="console">
<div class="row">
  <select id="runtenant" title="Client workspace"></select>
  <select id="rundrafter"></select>
  <button class="primary" id="runbtn">Run questionnaire</button>
  <span class="spin" id="runspin">running pipeline&hellip;</span>
</div>
<div class="result" id="runresult">
  <div class="grid" id="tiles"></div>
  <div class="row">
    <a class="filelink" id="rlink" target="_blank">open run report &rarr;</a>
    <a class="filelink" id="dlink">download DELIVERED.xlsx &darr;</a>
    <a class="filelink" id="alink" target="_blank">audit log (hash-chained) &rarr;</a>
  </div>
</div>
</div>

<footer>Pramana · synthetic tenant data only · release rule: zero unsupported material claims.</footer>
</div>
<script>
const $=id=>document.getElementById(id);
function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;
  if(text!==undefined&&text!==null)n.textContent=text;return n;}
function clear(n){while(n.firstChild)n.removeChild(n.firstChild);}
async function boot(){
  const opts=await (await fetch('/api/options')).json();
  for(const sel of [$('drafter'),$('rundrafter')]){
    clear(sel);
    for(const d of opts.drafters){
      const o=document.createElement('option');
      o.value=d.id;o.disabled=!d.available;
      o.textContent=`${d.label}${d.available?'':' — set API key'}`;
      sel.appendChild(o);
    }
  }
  const tsel=[$('tenant'),$('runtenant')];
  for(const sel of tsel){
    clear(sel);
    for(const t of opts.tenants){
      const o=document.createElement('option');o.value=t.slug;
      o.textContent=`${t.label} — ${t.sources} source${t.sources===1?'':'s'}`;
      sel.appendChild(o);
    }
  }
  const syncMeta=()=>{
    const t=opts.tenants.find(x=>x.slug===$('tenant').value)||opts.tenants[0];
    if(!t)return;
    $('tenantmeta').textContent=`workspace=${t.slug} · ${t.sources} approved source(s)`+
      (t.staged?` · ${t.staged} awaiting review`:'')+` · questionnaire=${t.questionnaire}`+
      ` · gates: cite-or-abstain · cert-evidence-class · staleness · contradiction · legal-routing · tenant-isolation`;
  };
  for(const sel of tsel) sel.onchange=()=>{
    for(const other of tsel) other.value=sel.value;
    syncMeta();
  };
  syncMeta();
  clear($('chips'));
  for(const q of opts.demo){
    const b=el('button',null,q);b.type='button';
    b.onclick=()=>{$('q').value=q;};
    $('chips').appendChild(b);
  }
}
function chipClass(v){
  if(v.startsWith('CITED · GATE-CLEAN'))return 'chip c-ok';
  if(v.startsWith('CITED'))return 'chip c-rev';
  return 'chip c-warn';
}
$('ask').onclick=async()=>{
  const q=$('q').value.trim(); if(!q)return;
  $('askspin').style.display='inline';$('askresult').style.display='none';$('ask').disabled=true;
  try{
    const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:q,drafter:$('drafter').value,tenant:$('tenant').value})});
    const data=await r.json();
    if(data.error)throw new Error(data.error);
    const c=data.contract;
    // SECURITY: an answer is a paragraph lifted verbatim from a client document,
    // and a client document is attacker-influenced input. Assigning it to
    // innerHTML would execute markup planted in an ingested PDF inside the
    // analyst's own browser — with access to every workspace on this console.
    // Everything derived from the engine is set as text, never parsed as HTML.
    $('verdict').textContent=data.verdict;$('verdict').className=chipClass(data.verdict);
    clear($('answer'));
    if(c.answer){$('answer').appendChild(document.createTextNode(c.answer));}
    else{$('answer').appendChild(el('em',null,'No answer released.'));}
    clear($('prov'));
    if(c.citations.length){
      const box=el('div','prov');
      c.citations.forEach((x,i)=>{
        if(i)box.appendChild(document.createElement('br'));
        box.appendChild(document.createTextNode(`${x.source_id} · v${x.version} · ${x.location}`));
      });
      $('prov').appendChild(box);
    }else{
      $('prov').appendChild(el('div','prov p-warn',`no citation released · ${c.route||'no-evidence'}`));
    }
    clear($('gaps'));
    c.gaps.forEach(g=>$('gaps').appendChild(el('div','gap','▸ '+g)));
    $('meta').textContent=`coverage=${c.evidence_coverage} · risk=${c.risk} · drafter=${c.drafter} (${c.model_version})`
      +` · human_review=${c.requires_human?'required':'not required'}`+(c.gate_flags.length?` · flags: ${c.gate_flags.join(' | ')}`:'');
    $('askresult').style.display='block';
  }catch(e){alert('Engine error: '+e.message);}
  $('askspin').style.display='none';$('ask').disabled=false;
};
$('runbtn').onclick=async()=>{
  $('runspin').style.display='inline';$('runresult').style.display='none';$('runbtn').disabled=true;
  try{
    const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({drafter:$('rundrafter').value,tenant:$('runtenant').value})});
    const data=await r.json();
    if(data.error)throw new Error(data.error);
    const m=data.metrics;
    const tile=(v,l,cls='')=>{
      const d=el('div','stat'+(cls?' '+cls:''));
      d.appendChild(el('b',null,v));d.appendChild(el('span',null,l));
      return d;
    };
    clear($('tiles'));
    [tile(m.questions,'questions'),
     tile(Math.round(m.cited_draft_coverage*100)+'%','cited coverage','ok'),
     tile(Math.round(m.abstention_rate*100)+'%','refusals (by design)','warn'),
     tile(m.exception_queue,'exceptions → humans','warn'),
     tile(m.unsupported_material_claims,'unsupported claims (must be 0)', m.unsupported_material_claims===0?'ok':'bad'),
     tile(m.audit_chain_valid?'VALID':'BROKEN','audit chain', m.audit_chain_valid?'ok':'bad'),
    ].forEach(t=>$('tiles').appendChild(t));
    $('rlink').href=data.report;$('dlink').href=data.delivered;$('alink').href=data.audit;
    $('runresult').style.display='block';
  }catch(e){alert('Engine error: '+e.message);}
  $('runspin').style.display='none';$('runbtn').disabled=false;
};
boot();
</script></body></html>"""


REVIEW_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pramana human review</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>/*CSS*/</style></head><body><div class="wrap">
<header>
<div class="eyebrow">Pramana &middot; Human Review</div>
<h1>A named person takes responsibility for every delivered answer.</h1>
<div class="runmeta" id="runmeta">decisions extend the run&rsquo;s own hash chain &middot; approve accepts only what the gates released &middot; an edited answer is HUMAN_AUTHORED, not evidence-backed</div>
<div class="navlinks"><a href="/">&larr; back to the answer console</a></div>
</header>

<h2>Reviewer</h2>
<p class="sub">Your name is recorded on every decision, alongside the operating-system identity of
whoever is running this console. It is self-asserted, not authenticated &mdash; and the audit log says so.</p>
<div class="console">
  <label class="fieldlabel" for="actor">Reviewer (name and email)</label>
  <div class="row">
    <input type="text" id="actor" placeholder="Priya Nair &lt;priya@company.com&gt;" autocomplete="off">
  </div>
  <label class="fieldlabel" for="runsel" style="margin-top:16px">Run</label>
  <div class="row">
    <select id="runsel" title="Runs under runs/, most recently touched first"></select>
    <label class="inline"><input type="checkbox" id="pendingonly"> pending only</label>
    <button id="reload" type="button">Load queue</button>
    <button class="primary" id="exportbtn" type="button">Export delivered workbook</button>
    <span class="spin" id="spin">working&hellip;</span>
  </div>
  <div class="row">
    <a class="filelink" id="exportlink" style="display:none"></a>
    <a class="filelink" id="reportlink" target="_blank" style="display:none">run report &rarr;</a>
    <a class="filelink" id="auditlink" target="_blank" style="display:none">audit log (hash-chained) &rarr;</a>
  </div>
  <div class="msg" id="msg"></div>
</div>

<h2>Review queue</h2>
<p class="sub">Every item shows the answer the engine released, the sources it survived the gates on,
and the gaps recorded against it. Approve accepts the cited answer as written. Edit replaces it with
your own words and labels it HUMAN_AUTHORED. Reject withdraws it and routes the question back.</p>
<div class="grid" id="sumtiles"></div>
<div id="queue"></div>

<footer>Pramana &middot; synthetic tenant data only &middot; every decision is appended to the run&rsquo;s signed, hash-chained audit log.</footer>
</div>
<script>
const $=id=>document.getElementById(id);
function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;
  if(text!==undefined&&text!==null)n.textContent=text;return n;}
function clear(n){while(n.firstChild)n.removeChild(n.firstChild);}
// SECURITY: an answer, a gap and a citation are all text lifted from a client
// document, and a client document is attacker-influenced input. Everything the
// engine returns is placed with textContent and never parsed as markup, so
// script planted in an ingested PDF cannot run in the reviewer's browser.
const STATUS_CHIP={evidence_backed:'c-ok',partial:'c-warn',requires_human:'c-rev',
  no_evidence:'c-bad',routed:'c-rev',human_authored:'c-warn'};
const ACTOR_KEY='pramana.reviewer';

function label(s){return String(s||'').replace(/_/g,' ').toUpperCase();}
function busy(on){$('spin').style.display=on?'inline':'none';
  for(const id of ['reload','exportbtn'])$(id).disabled=on;}
function setMsg(text,kind){const m=$('msg');m.className='msg'+(kind?' '+kind:'');m.textContent=text||'';}
function currentRun(){return $('runsel').value;}

async function api(path,opts){
  const r=await fetch(path,opts);
  let data;
  try{data=await r.json();}catch(e){throw new Error('HTTP '+r.status);}
  if(data&&data.error)throw new Error(data.error);
  return data;
}

async function loadRuns(){
  const data=await api('/api/review/runs');
  const sel=$('runsel');clear(sel);
  if(!data.runs.length){
    const o=document.createElement('option');o.value='';o.textContent='no reviewable runs yet';
    sel.appendChild(o);
    $('queue').appendChild(el('div','rev-empty',
      'No run under runs/ has a manifest.json and contracts.json yet. Run a questionnaire first.'));
    return false;
  }
  for(const r of data.runs){
    const o=document.createElement('option');o.value=r.run;
    o.textContent=`${r.run} — ${r.tenant} · ${r.decided}/${r.questions} decided`;
    sel.appendChild(o);
  }
  const wanted=new URLSearchParams(location.search).get('run');
  if(wanted&&data.runs.some(r=>r.run===wanted))sel.value=wanted;
  return true;
}

function renderSummary(s){
  const tile=(v,l,cls)=>{const d=el('div','stat'+(cls?' '+cls:''));
    d.appendChild(el('b',null,String(v)));d.appendChild(el('span',null,l));return d;};
  clear($('sumtiles'));
  [tile(`${s.reviewed}/${s.questions}`,'reviewed',s.reviewed?'ok':''),
   tile(s.pending,'pending',s.pending?'warn':'ok'),
   tile(Math.round(s.zero_human_edit_rate*100)+'%','zero human edit rate'),
   tile(s.audit_chain_valid?'VALID':'BROKEN','audit chain',s.audit_chain_valid?'ok':'bad'),
  ].forEach(t=>$('sumtiles').appendChild(t));
  $('runmeta').textContent=`run=${s.run} · workspace=${s.tenant} · ${s.questions} question(s) · `+
    `approved ${s.actions.approve} · edited ${s.actions.edit} · rejected ${s.actions.reject}`+
    (s.reviewers.length?` · reviewers: ${s.reviewers.join(', ')}`:'');
}

function renderItem(item){
  const card=el('div','rev-item'+(item.decided?' is-decided':''));
  const head=el('div','rev-head');
  head.appendChild(el('span','qid',item.question_id));
  if(item.domain)head.appendChild(el('span','dom',item.domain));
  head.appendChild(el('span','chip '+(STATUS_CHIP[item.status]||'c-rev'),label(item.status)));
  if(item.route)head.appendChild(el('span','dom','routed → '+item.route));
  card.appendChild(head);
  card.appendChild(el('div','rev-q',item.text));

  const ans=el('div','answer-box');
  if(item.answer)ans.appendChild(document.createTextNode(item.answer));
  else ans.appendChild(el('em',null,'No answer released — the gates found nothing approved to cite.'));
  card.appendChild(ans);

  if(item.citations.length){
    const box=el('div','prov');
    item.citations.forEach((c,i)=>{
      if(i)box.appendChild(document.createElement('br'));
      box.appendChild(document.createTextNode(`${c.source_id} · v${c.version} · ${c.location}`));});
    card.appendChild(box);
  }else{
    card.appendChild(el('div','prov p-warn','no citation released · '+(item.route||'no-evidence')));
  }
  item.gaps.forEach(g=>card.appendChild(el('div','gap','▸ '+g)));
  if(item.gate_flags.length)card.appendChild(el('div','small','flags: '+item.gate_flags.join(' | ')));

  if(item.decided){
    const d=item.decided;
    card.appendChild(el('div','decided',
      `${d.action.toUpperCase()} by ${d.actor} · ${d.timestamp}`+(d.note?` · note: ${d.note}`:'')));
  }

  const canApprove=item.allowed.indexOf('approve')>=0;
  if(!canApprove){
    card.appendChild(el('div','blocked',
      `Approve is unavailable here: this answer is ${label(item.status)} — the gates released `+
      `nothing for you to accept, and approving cannot manufacture evidence. Use Edit to supply a `+
      `human-authored answer (it is recorded HUMAN_AUTHORED and is not evidence-backed), or Reject.`));
  }

  const editbox=el('div','editbox');
  editbox.appendChild(el('div','editwarn','⚠ Human-authored · not evidence-backed'));
  editbox.appendChild(el('div','editnote',
    'What you write here replaces the engine\\'s answer. It is recorded as HUMAN_AUTHORED and '+
    'attributed to you: the delivered workbook and the audit log both state that it is not '+
    'supported by an approved source. Nothing you type creates evidence.'));
  const ta=document.createElement('textarea');
  ta.placeholder='The answer you are taking responsibility for…';
  if(item.decided&&item.decided.action==='edit'&&item.decided.answer_after)
    ta.value=item.decided.answer_after;
  editbox.appendChild(ta);

  const note=document.createElement('input');
  note.type='text';note.placeholder='note (optional — recorded in the audit log)';

  const saveRow=el('div','row');
  const save=el('button','primary','Record as HUMAN_AUTHORED');save.type='button';
  save.onclick=()=>decide(item,'edit',ta.value,note.value);
  saveRow.appendChild(save);
  editbox.appendChild(saveRow);

  const row=el('div','row');
  const approve=el('button','primary',canApprove?'Approve':'Approve — unavailable');
  approve.type='button';approve.disabled=!canApprove;
  approve.title=canApprove?'Accept the cited answer exactly as the gates released it'
    :'nothing was released for you to approve';
  approve.onclick=()=>decide(item,'approve',null,note.value);
  row.appendChild(approve);

  const editBtn=el('button',null,'Edit — write a human answer');editBtn.type='button';
  editBtn.onclick=()=>editbox.classList.toggle('open');
  row.appendChild(editBtn);

  const reject=el('button',null,'Reject');reject.type='button';
  reject.onclick=()=>decide(item,'reject',null,note.value);
  row.appendChild(reject);
  row.appendChild(note);
  card.appendChild(row);
  card.appendChild(editbox);
  return card;
}

async function loadQueue(){
  const run=currentRun();
  clear($('queue'));clear($('sumtiles'));
  for(const id of ['exportlink','reportlink','auditlink'])$(id).style.display='none';
  if(!run)return;
  busy(true);
  try{
    const data=await api('/api/review/queue?run='+encodeURIComponent(run)+
      ($('pendingonly').checked?'&pending=1':''));
    renderSummary(data.summary);
    if(data.delivered){const a=$('exportlink');a.href=data.delivered.file;
      a.textContent='latest workbook: '+data.delivered.name+' ↓';a.style.display='inline';}
    if(data.report){$('reportlink').href=data.report;$('reportlink').style.display='inline';}
    if(data.audit){$('auditlink').href=data.audit;$('auditlink').style.display='inline';}
    if(!data.items.length){
      $('queue').appendChild(el('div','rev-empty',
        'Nothing pending — every question in this run has been decided.'));
    }else{
      data.items.forEach(item=>$('queue').appendChild(renderItem(item)));
    }
  }catch(e){setMsg(e.message,'err');}
  busy(false);
}

async function decide(item,action,answer,note){
  const actor=$('actor').value.trim();
  try{localStorage.setItem(ACTOR_KEY,actor);}catch(e){}
  setMsg('');busy(true);
  const y=window.scrollY;
  try{
    const data=await api('/api/review/decide',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({run:currentRun(),question_id:item.question_id,action:action,
        actor:actor,note:note||'',answer:(answer===undefined?null:answer)})});
    busy(false);
    await loadQueue();
    window.scrollTo(0,y);
    setMsg(`${item.question_id}: ${action} recorded by ${data.decision.actor} → status `+
      `${label(data.item?data.item.status:'')} · audit chain `+
      `${data.summary.audit_chain_valid?'valid':'BROKEN'}`,'ok');
    return;
  }catch(e){setMsg(e.message,'err');}
  busy(false);
}

$('exportbtn').onclick=async()=>{
  if(!currentRun())return;
  setMsg('');busy(true);
  try{
    const data=await api('/api/review/export',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({run:currentRun()})});
    const a=$('exportlink');a.href=data.file;a.textContent='download '+data.name+' ↓';
    a.style.display='inline';
    renderSummary(data.summary);
    setMsg('exported '+data.name+' — reflects every decision recorded so far','ok');
  }catch(e){setMsg(e.message,'err');}
  busy(false);
};
$('reload').onclick=loadQueue;
$('runsel').onchange=loadQueue;
$('pendingonly').onchange=loadQueue;

async function boot(){
  try{const saved=localStorage.getItem(ACTOR_KEY);if(saved)$('actor').value=saved;}catch(e){}
  try{
    if(await loadRuns())await loadQueue();
  }catch(e){setMsg(e.message,'err');}
}
boot();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                page = PAGE.replace("/*CSS*/", CSS + EXTRA_CSS)
                self._send(200, page.encode(), "text/html; charset=utf-8")
            elif path in ("/review", "/review/"):
                page = REVIEW_PAGE.replace("/*CSS*/", CSS + EXTRA_CSS + REVIEW_CSS)
                self._send(200, page.encode(), "text/html; charset=utf-8")
            elif path == "/api/options":
                self._json({"drafters": drafter_options(), "demo": DEMO_QUESTIONS,
                            "tenants": tenant_options()})
            elif path == "/api/review/runs":
                self._json({"runs": review_runs()})
            elif path == "/api/review/queue":
                self._json(review_queue(
                    (query.get("run") or [""])[0],
                    pending_only=(query.get("pending") or ["0"])[0] in ("1", "true")))
            elif path.startswith("/runs/"):
                target = (ROOT / path.lstrip("/")).resolve()
                if not target.is_relative_to(RUNS.resolve()) or not target.is_file():
                    self._send(404, b"not found", "text/plain")
                    return
                ctype = {"html": "text/html; charset=utf-8", "jsonl": "text/plain",
                         "json": "application/json",
                         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         }.get(target.suffix.lstrip("."), "application/octet-stream")
                self._send(200, target.read_bytes(), ctype)
            else:
                self._send(404, b"not found", "text/plain")
        except ReviewError as exc:
            # the review rules are the product speaking — quote them verbatim
            self._json({"error": str(exc)}, code=400)
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, code=500)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        path = urlparse(self.path).path
        try:
            load_env(ROOT)
            body = json.loads(self.rfile.read(length) or b"{}")
            if path == "/api/ask":
                self._json(answer_one(body["question"], body.get("drafter", "mock"),
                                      tenant=body.get("tenant", "acme")))
            elif path == "/api/run":
                self._json(run_batch(body.get("drafter", "mock"),
                                     tenant=body.get("tenant", "acme")))
            elif path == "/api/review/decide":
                self._json(review_decide(body))
            elif path == "/api/review/export":
                self._json(review_export(body.get("run") or ""))
            else:
                self._send(404, b"not found", "text/plain")
        except ReviewError as exc:
            # a refused decision is the process working. Show the reviewer the
            # engine's own words rather than a generic failure.
            self._json({"error": str(exc)}, code=400)
        except Exception as exc:  # fail loudly to the UI, never fabricate an answer
            self._json({"error": f"{type(exc).__name__}: {exc}"}, code=500)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[pramana-console] {self.address_string()} {fmt % args}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pramana zero-dependency web console")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Pramana console → http://localhost:{args.port}  (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
