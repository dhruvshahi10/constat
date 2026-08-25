"""Constat console — zero-dependency web UI over the evidence-gated engine.

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
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from constat.drafter import make_drafter                     # noqa: E402
from constat.envfile import load_env                         # noqa: E402
from constat.evidence import EvidenceStore                   # noqa: E402
from constat.gates import post_gate, pre_gate                # noqa: E402
from constat.models import Draft, Question                   # noqa: E402
from constat.pipeline import run                             # noqa: E402
from constat.report import CSS, write_report                 # noqa: E402
from constat.retrieve import Retriever                       # noqa: E402

import os                                                     # noqa: E402

EVIDENCE = ROOT / "data" / "evidence"
QNR = ROOT / "data" / "questionnaires" / "acme_security_questionnaire.xlsx"
RUNS = ROOT / "runs"

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

    d = Draft(question_id=q.question_id, answer=None)
    d = pre_gate(q, d)
    if d.route != "LEGAL":
        d = make_drafter(drafter_kind, retriever).draft(q, tenant)
        d = pre_gate(q, d)
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
    res = run(QNR, tenant=tenant, evidence_root=EVIDENCE, out_dir=out,
              drafter_kind=drafter_kind, today=date.today())
    report = write_report(res, date.today())
    rel = out.relative_to(ROOT).as_posix()
    return {
        "metrics": res.metrics,
        "report": f"/{rel}/{report.name}",
        "delivered": f"/{rel}/{res.delivered_xlsx.name}",
        "audit": f"/{rel}/{res.audit_path.name}",
    }


EXTRA_CSS = """
.console{background:var(--surface-card);border:1px solid var(--line-1);border-left:2px solid var(--signal);
border-radius:var(--radius-2);padding:20px 22px;margin:20px 0}
textarea{width:100%;min-height:64px;font-family:var(--font-sans);font-size:14px;line-height:1.5;
color:var(--text-primary);background:var(--surface-sunken);border:1px solid var(--line-1);
border-radius:var(--radius-1);padding:11px 13px;resize:vertical}
textarea::placeholder{color:var(--text-tertiary)}
select,button{font-family:var(--font-mono);font-size:11px;letter-spacing:0.1em;text-transform:uppercase;
padding:10px 15px;border:1px solid var(--line-2);border-radius:var(--radius-1);
background:var(--surface-raised);color:var(--text-primary);cursor:pointer;
transition:border-color 240ms cubic-bezier(0.19,1,0.22,1),color 240ms cubic-bezier(0.19,1,0.22,1)}
select:hover,button:hover{border-color:var(--line-3)}
button.primary{background:var(--signal);color:var(--signal-ink);border-color:var(--signal)}
button.primary:hover{background:var(--signal-bright);border-color:var(--signal-bright)}
button:disabled{opacity:.4;cursor:not-allowed}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:14px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.chips button{padding:6px 10px;text-transform:none;letter-spacing:0;color:var(--text-tertiary);
background:transparent;font-size:11.5px}
.chips button:hover{color:var(--text-primary);border-color:var(--line-signal)}
.result{margin-top:20px;display:none}
.answer-box{border:1px solid var(--line-1);border-radius:var(--radius-1);background:var(--surface-sunken);
padding:15px 17px;margin-top:12px;font-size:14px;color:var(--text-primary)}
.spin{display:none;font-family:var(--font-mono);font-size:11px;color:var(--signal)}
a.filelink{font-family:var(--font-mono);font-size:11px;letter-spacing:0.08em;color:var(--signal)}
/* --text-faint is hairline-only now; it fails contrast as text (see brand.py) */
.small{font-family:var(--font-mono);font-size:10.5px;line-height:1.8;color:var(--text-tertiary);margin-top:10px}
"""

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Constat console</title>
<style>/*CSS*/</style></head><body><div class="wrap">
<header>
<div class="eyebrow"><b>Constat</b> / Evidence gated answer engine / v0</div>
<h1>Every answer cited to an approved source, <i>or refused.</i></h1>
<div class="runmeta">tenant=acme (synthetic)<br>gates: cite-or-abstain / cert-evidence-class /
staleness / contradiction / legal-routing / tenant-isolation</div>
</header>

<div class="seclabel"><span class="idx">01</span><span class="label">Single question</span><span class="rule"></span></div>
<h2>Ask a security question</h2>
<p class="sub">The selected model drafts. Every citation must then survive the deterministic gates.
No surviving citation &rarr; the engine refuses and names the gap. Try the planted traps below.</p>
<div class="console">
<textarea id="q" placeholder="e.g. Is customer data encrypted in transit?"></textarea>
<div class="chips" id="chips"></div>
<div class="row">
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

<div class="seclabel"><span class="idx">02</span><span class="label">Full workbook</span><span class="rule"></span></div>
<h2>Run the full questionnaire</h2>
<p class="sub">The 24-question CAIQ-style workbook end to end: ingest &rarr; classify &rarr; draft &rarr;
gates &rarr; simulated review &rarr; export. Produces the audit working paper, the DELIVERED workbook,
and the hash-chained audit log.</p>
<div class="console">
<div class="row">
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

<footer>Constat v0 · synthetic tenant data only · release rule: zero unsupported material claims.</footer>
</div>
<script>
const $=id=>document.getElementById(id);
/* dnode(tag, className, text): an answer is a paragraph lifted verbatim from a
   governed document, and a citation and a gap message both quote one. They are
   written as text nodes, never assembled into markup, so nothing an ingested
   document contains can execute in this console. */
const dnode=(tag,cls,text)=>{const n=document.createElement(tag);
  if(cls)n.className=cls;
  if(text!=null)n.textContent=String(text);
  return n};
async function boot(){
  const opts=await (await fetch('/api/options')).json();
  for(const sel of [$('drafter'),$('rundrafter')]){
    sel.innerHTML=opts.drafters.map(d=>`<option value="${d.id}" ${d.available?'':'disabled'}>`+
      `${d.label}${d.available?'':' / set API key'}</option>`).join('');
  }
  $('chips').innerHTML=opts.demo.map(q=>`<button type="button">${q}</button>`).join('');
  for(const b of $('chips').querySelectorAll('button')) b.onclick=()=>{$('q').value=b.textContent;};
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
      body:JSON.stringify({question:q,drafter:$('drafter').value})});
    const data=await r.json();
    if(data.error)throw new Error(data.error);
    const c=data.contract;
    $('verdict').textContent=data.verdict;$('verdict').className=chipClass(data.verdict);
    $('answer').replaceChildren(c.answer?document.createTextNode(c.answer)
      :dnode('em',null,'No answer released.'));
    const prov=dnode('div',c.citations.length?'prov':'prov p-warn');
    if(c.citations.length)c.citations.forEach((x,i)=>{
      if(i)prov.append(document.createElement('br'));
      prov.append(document.createTextNode(
        `${x.source_id} · v${x.version} · ${x.location}`));
    });
    else prov.textContent=`no citation released · ${c.route||'no-evidence'}`;
    $('prov').replaceChildren(prov);
    $('gaps').replaceChildren(...c.gaps.map(g=>{
      const d=dnode('div','gap');
      d.append(document.createTextNode('\u25B8 '),document.createTextNode(String(g)));
      return d;
    }));
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
      body:JSON.stringify({drafter:$('rundrafter').value})});
    const data=await r.json();
    if(data.error)throw new Error(data.error);
    const m=data.metrics;
    const tile=(v,l,cls='')=>`<div class="stat ${cls}"><b>${v}</b><span>${l}</span></div>`;
    $('tiles').innerHTML=tile(m.questions,'questions')+
      tile(Math.round(m.cited_draft_coverage*100)+'%','cited coverage','ok')+
      tile(Math.round(m.abstention_rate*100)+'%','refusals (by design)','warn')+
      tile(m.exception_queue,'exceptions &rarr; humans','warn')+
      tile(m.ungrounded_refusals??0,'answers refused as ungrounded', (m.ungrounded_refusals??0)===0?'ok':'warn')+
      tile(m.citations_dropped??0,'citations dropped by the gates', (m.citations_dropped??0)===0?'ok':'warn')+
      tile(m.audit_chain_valid?'VALID':'BROKEN','audit chain', m.audit_chain_valid?'ok':'bad');
    $('rlink').href=data.report;$('dlink').href=data.delivered;$('alink').href=data.audit;
    $('runresult').style.display='block';
  }catch(e){alert('Engine error: '+e.message);}
  $('runspin').style.display='none';$('runbtn').disabled=false;
};
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
        if self.path in ("/", "/index.html"):
            page = PAGE.replace("/*CSS*/", CSS + EXTRA_CSS)
            self._send(200, page.encode(), "text/html; charset=utf-8")
        elif self.path == "/api/options":
            self._json({"drafters": drafter_options(), "demo": DEMO_QUESTIONS})
        elif self.path.startswith("/runs/"):
            target = (ROOT / self.path.lstrip("/")).resolve()
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

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        try:
            load_env(ROOT)
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/ask":
                self._json(answer_one(body["question"], body.get("drafter", "mock")))
            elif self.path == "/api/run":
                self._json(run_batch(body.get("drafter", "mock")))
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as exc:  # fail loudly to the UI, never fabricate an answer
            self._json({"error": f"{type(exc).__name__}: {exc}"}, code=500)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[constat-console] {self.address_string()} {fmt % args}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Constat zero-dependency web console")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Constat console → http://localhost:{args.port}  (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
