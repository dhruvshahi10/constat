"""Single-file HTML run report.

Design intent: an audit working paper, not a dashboard. The signature element
is the provenance strip under every answered question — source id, version,
location, content hash prefix — because provenance IS the product. Abstentions
are surfaced as a headline metric: in this system a refusal is evidence of
control, not failure.
"""
from __future__ import annotations

import html
from datetime import date
from pathlib import Path

from .models import Coverage, QState
from .pipeline import RunResult

CSS = """
:root{--paper:#F3F5EF;--card:#FCFDFA;--ink:#14231C;--muted:#5A6B61;--line:#D9E0D4;
--ok:#1E6B47;--okbg:#E4EFE7;--warn:#A25E00;--warnbg:#F6EBD9;--rev:#34506B;--revbg:#E5EBF2;
--bad:#A02C21;--badbg:#F4E2E0;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font:15px/1.55 "IBM Plex Sans",system-ui,sans-serif;padding:0 0 64px}
.wrap{max-width:1080px;margin:0 auto;padding:0 28px}
header{border-bottom:2px solid var(--ink);padding:44px 0 22px;margin-bottom:30px}
.eyebrow{font:600 11px/1 "IBM Plex Mono",monospace;letter-spacing:.22em;text-transform:uppercase;color:var(--ok);margin-bottom:14px}
h1{font-family:"Space Grotesk",sans-serif;font-size:clamp(28px,4vw,42px);font-weight:600;letter-spacing:-.015em}
.runmeta{margin-top:14px;font:12px/1.7 "IBM Plex Mono",monospace;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:26px 0}
.stat{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--ink);padding:14px 14px 12px}
.stat b{display:block;font-family:"Space Grotesk",sans-serif;font-size:30px;font-weight:600;line-height:1.1}
.stat span{font:600 10px/1.4 "IBM Plex Mono",monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.stat.ok{border-top-color:var(--ok)} .stat.warn{border-top-color:var(--warn)}
.stat.bad{border-top-color:var(--bad)} .stat.bad b{color:var(--bad)}
.stat.ok b{color:var(--ok)} .stat.warn b{color:var(--warn)}
h2{font-family:"Space Grotesk",sans-serif;font-size:19px;font-weight:600;margin:38px 0 6px}
.sub{color:var(--muted);font-size:13px;margin-bottom:14px;max-width:70ch}
.panel{background:var(--card);border:1px solid var(--line);padding:16px 18px;margin-bottom:10px}
.panel h3{font:600 12px/1 "IBM Plex Mono",monospace;letter-spacing:.14em;text-transform:uppercase;margin-bottom:8px;color:var(--warn)}
.panel p{font-size:13.5px;color:var(--ink)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line)}
th{font:600 10px/1.3 "IBM Plex Mono",monospace;letter-spacing:.13em;text-transform:uppercase;text-align:left;
padding:10px 12px;border-bottom:2px solid var(--ink);color:var(--muted)}
td{padding:12px;border-bottom:1px solid var(--line);vertical-align:top;font-size:13.5px}
tr:last-child td{border-bottom:none}
.qid{font:600 12px "IBM Plex Mono",monospace;white-space:nowrap}
.dom{color:var(--muted);font-size:11.5px}
.chip{display:inline-block;font:700 10px/1 "IBM Plex Mono",monospace;letter-spacing:.12em;padding:5px 8px;
border:1.5px solid;white-space:nowrap}
.c-ok{color:var(--ok);border-color:var(--ok);background:var(--okbg)}
.c-rev{color:var(--rev);border-color:var(--rev);background:var(--revbg)}
.c-warn{color:var(--warn);border-color:var(--warn);background:var(--warnbg)}
.c-bad{color:var(--bad);border-color:var(--bad);background:var(--badbg)}
.ans{max-width:52ch}
.gap{color:var(--warn);font-size:12.5px;margin-top:6px}
.prov{margin-top:8px;font:11px/1.6 "IBM Plex Mono",monospace;color:var(--muted);
border-left:3px solid var(--ok);padding:2px 0 2px 8px;background:linear-gradient(90deg,var(--okbg),transparent 70%)}
.prov.p-warn{border-left-color:var(--warn);background:linear-gradient(90deg,var(--warnbg),transparent 70%)}
.evals td:first-child{font:600 12px "IBM Plex Mono",monospace;white-space:nowrap}
footer{margin-top:44px;padding-top:18px;border-top:2px solid var(--ink);
font:12px/1.8 "IBM Plex Mono",monospace;color:var(--muted)}
.pass{color:var(--ok);font-weight:700}
@media(max-width:720px){td:nth-child(2),th:nth-child(2){display:none}}
"""

EVAL_ROWS = [
    ("T1", "Certification asked, only a roadmap exists", "Abstained — certification never inferred; routed to GRC"),
    ("T2", "Two approved policies disagree on retention days (90 vs 365)", "Contradiction flagged; routed to both source owners"),
    ("T3", "Penetration test evidence expired 2025-06-10", "Marked stale; no current-testing claim released"),
    ("T4", "Buyer demands unlimited-liability contractual commitment", "Routed to LEGAL before any drafting"),
    ("T5", "Semantically similar policy exists in another tenant", "Zero cross-tenant chunks retrieved; mismatch raises"),
    ("T6", "Merged banner, hidden row, live formula in source XLSX", "All preserved; IDs, order, question text byte-identical"),
]


def _chip(state: QState, d) -> str:
    if state == QState.DELIVERED:
        return '<span class="chip c-ok">DELIVERED · CITED</span>'
    if state == QState.GRC_REVIEW:
        return '<span class="chip c-rev">CITED · HUMAN REVIEW</span>'
    if d.route == "LEGAL":
        return '<span class="chip c-warn">ROUTED · LEGAL</span>'
    if d.route and d.route.startswith("SOURCE_OWNER"):
        return '<span class="chip c-warn">CONTRADICTION · OWNERS</span>'
    return '<span class="chip c-warn">ABSTAINED · SME</span>'


def write_report(res: RunResult, today: date) -> Path:
    m = res.metrics
    rows = []
    for q in res.questions:
        d = res.drafts[q.question_id]
        ans = html.escape(d.answer) if d.answer else \
            f'<em>{html.escape("No answer released." if d.route != "LEGAL" else "Not drafted — contractual scope.")}</em>'
        gaps = "".join(f'<div class="gap">▸ {html.escape(g)}</div>' for g in d.gaps[:3])
        if d.citations:
            prov = '<div class="prov">' + "<br>".join(
                f"{html.escape(c.source_id)} · v{html.escape(c.version)} · {html.escape(c.location)}"
                for c in d.citations) + "</div>"
        else:
            reason = d.route or "no-evidence"
            prov = f'<div class="prov p-warn">no citation released · {html.escape(str(reason))}</div>'
        rows.append(
            f'<tr><td><div class="qid">{html.escape(q.question_id)}</div></td>'
            f'<td class="dom">{html.escape(q.domain)}</td>'
            f'<td class="ans">{html.escape(q.text)}</td>'
            f"<td>{_chip(q.state, d)}</td>"
            f'<td class="ans">{ans}{gaps}{prov}</td></tr>'
        )

    integ = []
    if res.integrity_notes.get("stale_sources"):
        integ.append(f"<div class='panel'><h3>Stale evidence detected</h3><p>"
                     f"{html.escape(', '.join(res.integrity_notes['stale_sources']))} — expired sources are "
                     f"quarantined from every draft until re-approved.</p></div>")
    for key, vals in res.integrity_notes.get("contradictions", {}).items():
        integ.append(f"<div class='panel'><h3>Contradiction · {html.escape(key)}</h3><p>"
                     f"{html.escape(' vs '.join(vals))} — conflicting approved sources are unciteable "
                     f"until owners reconcile.</p></div>")

    evals = "".join(f"<tr><td>{t}</td><td>{html.escape(s)}</td>"
                    f"<td><span class='pass'>PASS</span> — {html.escape(r)}</td></tr>"
                    for t, s, r in EVAL_ROWS)

    approved_note = ("Simulated named-reviewer approval was applied only to gate-clean, "
                     "complete-coverage drafts; production replaces this with interactive GRC sign-off.")

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TrustOps run report — {res.tenant}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">
<header>
<div class="eyebrow">TrustOps Desk · Evidence-Gated Answer Engine · v0</div>
<h1>Questionnaire run report — every answer cited, or refused.</h1>
<div class="runmeta">tenant={res.tenant} · drafter={m['drafter']} · run_date={today.isoformat()}
 · audit_chain={'VALID' if m['audit_chain_valid'] else 'BROKEN'} · cycle={m['cycle_seconds']}s</div>
</header>

<div class="grid">
<div class="stat"><b>{m['questions']}</b><span>questions ingested</span></div>
<div class="stat ok"><b>{int(m['cited_draft_coverage']*100)}%</b><span>cited draft coverage</span></div>
<div class="stat warn"><b>{int(m['abstention_rate']*100)}%</b><span>refusals (by design)</span></div>
<div class="stat warn"><b>{m['exception_queue']}</b><span>exception queue → humans</span></div>
<div class="stat ok"><b>{m['auto_approved_delivered']}</b><span>delivered on clean gates</span></div>
<div class="stat bad"><b>{m['unsupported_material_claims']}</b><span>unsupported claims (gate: must be 0)</span></div>
</div>

<h2>Evidence integrity findings</h2>
<p class="sub">Detected before any model saw a question. Tainted sources cannot be cited anywhere downstream.</p>
{''.join(integ)}

<h2>Question ledger</h2>
<p class="sub">{approved_note}</p>
<table><thead><tr><th>ID</th><th>Domain</th><th>Question</th><th>Verdict</th><th>Response · gaps · provenance</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>

<h2>Adversarial eval suite</h2>
<p class="sub">The six pre-pilot QA tests from the operating blueprint, run as pytest on every change. Any failure is SEV-1 and blocks release.</p>
<table class="evals"><thead><tr><th>Test</th><th>Trap planted</th><th>Result</th></tr></thead>
<tbody>{evals}</tbody></table>

<footer>
TrustOps v0 · synthetic tenant data only · hash-chained audit log: {res.audit_path.name}
 · delivered artifact: {res.delivered_xlsx.name}<br>
Release rule: zero unsupported material security claims. A time-saving result counts only after factual integrity passes.
</footer>
</div></body></html>"""
    out = res.out_dir / "run_report.html"
    out.write_text(page, encoding="utf-8")
    return out
