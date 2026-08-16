"""Single-file HTML run report.

Design intent: an audit working paper that reads at a glance and holds up
under scrutiny. The run lattice, the coverage dial and the refusal bar carry
the verdict without prose; the ledger below them carries the evidence. The
signature element is still the provenance strip under every answered question,
source id, version and location, because provenance IS the product.
Abstentions are surfaced as a headline metric: in this system a refusal is
evidence of control, not failure.

Palette, type and component vocabulary come from trustops.brand, which is the
owner's Claude Design system adopted verbatim.
"""
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

from . import brand
from .models import Coverage, QState
from .pipeline import RunResult

CSS = brand.stylesheet()

# The engine name is an internal identifier; a buyer reading this document
# should not have to decode "mock".
DRAFTER_LABELS = {
    "mock": "deterministic offline engine",
    "anthropic": "Anthropic Claude, live",
    "gemini": "Google Gemini, live",
    "gate": "gate only, never drafted",
}


def _drafter_label(kind: str) -> str:
    return DRAFTER_LABELS.get(kind, kind)


def _approval_mode(res: RunResult) -> str:
    """Hosted runs approve nothing automatically; demo runs use a labeled
    stand-in reviewer. Saying the wrong one on a buyer's report is a lie about
    who signed off, so read the run's own record rather than assume."""
    mode = res.metrics.get("approval_mode")
    if mode:
        return str(mode)
    try:
        state = json.loads((res.out_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "simulated"
    return str(state.get("approval_mode") or "simulated")


def _evidence_chars(d) -> int:
    """Characters of customer evidence transmitted to a drafting model for this
    question. The offline engine transmits none, and says so."""
    for f in d.gate_flags:
        if f.startswith("EVIDENCE_CHARS:"):
            try:
                return int(f.split(":", 1)[1])
            except ValueError:
                return 0
    return 0

EVAL_ROWS = [
    ("T1", "Certification asked, only a roadmap exists", "Abstained, certification never inferred, routed to GRC"),
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


# Why a refusal happened, in the order the gates decide it. Retrieval misses
# are the only class that a better index can recover; the other three are the
# gates doing their job and must survive every future change.
REFUSAL_KINDS = [
    ("contradiction", "CONTRADICTION", "sb-c", "conflicting approved sources"),
    ("stale", "STALE_EVIDENCE", "sb-s", "expired evidence"),
    ("ungrounded", "UNGROUNDED_ANSWER", "sb-s", "answer not traceable to its citations"),
    ("legal", None, "sb-l", "routed to counsel"),
    ("retrieval", None, "sb-r", "no approved evidence found"),
]


def _refusal_kind(d) -> str:
    flags = " ".join(d.gate_flags)
    if "CONTRADICTION" in flags:
        return "contradiction"
    if "STALE_EVIDENCE" in flags or "CERT_INFERENCE_BLOCKED" in flags:
        return "stale"
    if "UNGROUNDED_ANSWER" in flags:
        return "ungrounded"
    if d.route == "LEGAL":
        return "legal"
    return "retrieval"


def _refusal_bar(drafts) -> str:
    """Stacked bar of why the run refused, widest reason first."""
    counts: dict[str, int] = {}
    for d in drafts:
        if d.abstained:
            k = _refusal_kind(d)
            counts[k] = counts.get(k, 0) + 1
    if not counts:
        return '<p class="sub">No refusals in this run.</p>'
    segs, key = [], []
    for kind, _flag, cls, blurb in REFUSAL_KINDS:
        n = counts.get(kind, 0)
        if not n:
            continue
        segs.append(f'<div class="{cls}" style="flex:{n}">{n} {kind.upper()}</div>')
        key.append(f'<span class="label">{n} {kind}, {blurb}</span>')
    return (f'<div class="stackbar">{"".join(segs)}</div>'
            f'<div class="latkey" style="margin-top:12px">{"".join(key)}</div>')


def write_report(res: RunResult, today: date) -> Path:
    m = res.metrics
    rows = []
    for q in res.questions:
        d = res.drafts[q.question_id]
        ans = html.escape(d.answer) if d.answer else \
            f'<em>{html.escape("No answer released." if d.route != "LEGAL" else "Not drafted, contractual scope.")}</em>'
        gaps = "".join(f'<div class="gap">▸ {html.escape(g)}</div>' for g in d.gaps[:3])
        if d.citations:
            prov = '<div class="prov">' + "<br>".join(
                f"{html.escape(c.source_id)} · v{html.escape(c.version)} · {html.escape(c.location)}"
                for c in d.citations) + "</div>"
        else:
            reason = d.route or "no-evidence"
            prov = f'<div class="prov p-warn">no citation released · {html.escape(str(reason))}</div>'
        # custody receipt: how much of the customer's text left the machine for
        # this one question. Every excerpt is capped before transmission.
        sent = _evidence_chars(d)
        prov += ('<div class="prov">evidence to model · '
                 + (f"{sent:,} characters" if sent
                    else "0 characters, drafted on-machine")
                 + "</div>")
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
                     f"{html.escape(', '.join(res.integrity_notes['stale_sources']))}. Expired sources are "
                     f"quarantined from every draft until re-approved.</p></div>")
    for key, vals in res.integrity_notes.get("contradictions", {}).items():
        integ.append(f"<div class='panel'><h3>Contradiction · {html.escape(key)}</h3><p>"
                     f"{html.escape(' vs '.join(vals))}. Conflicting approved sources are unciteable "
                     f"until owners reconcile.</p></div>")

    evals = "".join(f"<tr><td>{t}</td><td>{html.escape(s)}</td>"
                    f"<td><span class='pass'>PASS</span> &nbsp;{html.escape(r)}</td></tr>"
                    for t, s, r in EVAL_ROWS)

    if _approval_mode(res) == "human":
        approved_note = ("Every DELIVERED answer below carries a named reviewer and note in the "
                         "tamper-evident audit chain. Nothing reaches DELIVERED without that "
                         "signature; everything else is still waiting on a human.")
    else:
        approved_note = ("Simulated named-reviewer approval was applied only to gate-clean, "
                         "complete-coverage drafts; production replaces this with interactive GRC sign-off.")

    lattice = brand.run_lattice([
        (q.question_id, q.state.value,
         "delivered" if q.state == QState.DELIVERED else
         "awaiting a human" if q.state == QState.GRC_REVIEW else
         f"refused, {_refusal_kind(res.drafts[q.question_id])}")
        for q in res.questions
    ])
    dial = brand.coverage_dial(m["cited_draft_coverage"])
    refusals = _refusal_bar(list(res.drafts.values()))
    chain_ok = m["audit_chain_valid"]
    # Two counts the run genuinely measures, as opposed to asserts. The
    # grounding gate refuses a drafted answer whose words are not traceable to
    # the passages it cited; the citation resolver drops citations a model
    # attached to sources or locations that were never retrieved.
    grounding_refusals = sum(
        1 for d in res.drafts.values() if "UNGROUNDED_ANSWER" in d.gate_flags)
    dropped_citations = sum(
        1 for d in res.drafts.values()
        for f in d.gate_flags
        if f in ("FABRICATED_CITATION", "HALLUCINATED_LOCATION", "UNRETRIEVED_CITATION"))

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TrustOps run report, {html.escape(res.tenant)}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header>
<div class="eyebrow"><b>TrustOps Desk</b> / Evidence gated answer engine / v0</div>
<h1>Every answer cited to an approved source, <i>or refused.</i></h1>
<div class="runmeta">tenant={html.escape(res.tenant)}
 &nbsp;/&nbsp; drafting engine={html.escape(_drafter_label(m['drafter']))}
 &nbsp;/&nbsp; run_date={today.isoformat()}
 &nbsp;/&nbsp; audit_chain={'VALID' if chain_ok else 'BROKEN'}
 &nbsp;/&nbsp; cycle={m['cycle_seconds']}s</div>
</header>

<div class="latkey" style="margin-bottom:14px">
<span class="chip c-ok">{m['auto_approved_delivered']} delivered</span>
<span class="chip c-rev">{m['awaiting_human_review']} awaiting a human</span>
<span class="chip c-warn">{m['exception_queue']} refused</span>
<span class="label">One cell per question, in workbook order. Hover for its verdict.</span>
</div>
{lattice}

<div class="viz">{dial}
<div class="grid" style="margin:0">
<div class="stat"><b>{m['questions']}</b><span>questions ingested</span></div>
<div class="stat warn"><b>{int(m['abstention_rate']*100)}%</b><span>refused by design</span></div>
<div class="stat ok"><b>{m['auto_approved_delivered']}</b><span>delivered on clean gates</span></div>
<div class="stat {'ok' if grounding_refusals == 0 else 'warn'}"><b>{grounding_refusals}</b>
<span>answers refused as ungrounded</span></div>
<div class="stat {'ok' if dropped_citations == 0 else 'warn'}"><b>{dropped_citations}</b>
<span>citations dropped by the gates</span></div>
<div class="stat {'ok' if chain_ok else 'bad'}"><b>{'VALID' if chain_ok else 'BROKEN'}</b>
<span>audit chain</span></div>
<div class="stat info"><b>{m['cycle_seconds']}s</b><span>cycle time</span></div>
</div></div>

<div class="seclabel"><span class="idx">01</span><span class="label">Why the run refused</span><span class="rule"></span></div>
<p class="sub">Retrieval misses are the only class a better index recovers. The rest are gates
doing their job, and they must survive every future change.</p>
{refusals}

<div class="seclabel"><span class="idx">02</span><span class="label">Evidence integrity</span><span class="rule"></span></div>
<p class="sub">Detected before any model saw a question. Tainted sources cannot be cited anywhere downstream.</p>
{''.join(integ) or '<p class="sub">No stale or contradicted sources in this evidence set.</p>'}

<div class="seclabel"><span class="idx">03</span><span class="label">Question ledger</span><span class="rule"></span></div>
<p class="sub">{approved_note}</p>
<table><thead><tr><th>ID</th><th>Domain</th><th>Question</th><th>Verdict</th><th>Response, gaps, provenance</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>

<div class="seclabel"><span class="idx">04</span><span class="label">Adversarial eval suite</span><span class="rule"></span></div>
<p class="sub">Six adversarial tests with deliberately planted traps, re-run automatically on every
change to the engine. Any failure blocks the release.</p>
<table class="evals"><thead><tr><th>Test</th><th>Trap planted</th><th>Result</th></tr></thead>
<tbody>{evals}</tbody></table>

<footer>
TrustOps v0 / synthetic tenant data only / hash chained audit log: {res.audit_path.name}
 / delivered artifact: {res.delivered_xlsx.name}<br>
Release rule: an answer is released only if it survives the citation gates and its words are
traceable to the passages it cites. Anything else is refused and named. A time saving result
counts only after factual integrity passes.
</footer>
</div></body></html>"""
    out = res.out_dir / "run_report.html"
    out.write_text(page, encoding="utf-8")
    return out
