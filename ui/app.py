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
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
async function boot(){
  const opts=await (await fetch('/api/options')).json();
  for(const sel of [$('drafter'),$('rundrafter')]){
    sel.innerHTML=opts.drafters.map(d=>`<option value="${d.id}" ${d.available?'':'disabled'}>`+
      `${d.label}${d.available?'':' — set API key'}</option>`).join('');
  }
  const tsel=[$('tenant'),$('runtenant')];
  for(const sel of tsel){
    sel.innerHTML=opts.tenants.map(t=>`<option value="${t.slug}">${t.label} — ${t.sources} source${t.sources===1?'':'s'}</option>`).join('');
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
      body:JSON.stringify({question:q,drafter:$('drafter').value,tenant:$('tenant').value})});
    const data=await r.json();
    if(data.error)throw new Error(data.error);
    const c=data.contract;
    $('verdict').textContent=data.verdict;$('verdict').className=chipClass(data.verdict);
    $('answer').innerHTML=c.answer?c.answer:'<em>No answer released.</em>';
    $('prov').innerHTML=c.citations.length
      ?'<div class="prov">'+c.citations.map(x=>`${x.source_id} · v${x.version} · ${x.location}`).join('<br>')+'</div>'
      :`<div class="prov p-warn">no citation released · ${c.route||'no-evidence'}</div>`;
    $('gaps').innerHTML=c.gaps.map(g=>`<div class="gap">&#9656; ${g}</div>`).join('');
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
    const tile=(v,l,cls='')=>`<div class="stat ${cls}"><b>${v}</b><span>${l}</span></div>`;
    $('tiles').innerHTML=tile(m.questions,'questions')+
      tile(Math.round(m.cited_draft_coverage*100)+'%','cited coverage','ok')+
      tile(Math.round(m.abstention_rate*100)+'%','refusals (by design)','warn')+
      tile(m.exception_queue,'exceptions &rarr; humans','warn')+
      tile(m.unsupported_material_claims,'unsupported claims (must be 0)', m.unsupported_material_claims===0?'ok':'bad')+
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
            self._json({"drafters": drafter_options(), "demo": DEMO_QUESTIONS,
                        "tenants": tenant_options()})
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
                self._json(answer_one(body["question"], body.get("drafter", "mock"),
                                      tenant=body.get("tenant", "acme")))
            elif self.path == "/api/run":
                self._json(run_batch(body.get("drafter", "mock"),
                                     tenant=body.get("tenant", "acme")))
            else:
                self._send(404, b"not found", "text/plain")
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
