"""Commitment register — the gap between what sales promised and what GRC can evidence.

Security commitments are made on the sales side, in contracts, RFP responses and
DPAs, at the speed of a deal. Evidence is produced on the GRC side, at the speed
of a control. Nobody reconciles the two until an auditor, a customer, or an
incident does it for them.

This reuses the same machinery as questionnaire answering — retrieval, the
gates, the declared assertions — and turns it around: instead of asking "what
can we say?", it asks "we already said this; can we stand behind it?"

Four verdicts, in order of how much trouble they are:

  CONTRADICTED   evidence exists and it disagrees with the promise. A machine-
                 checkable assertion says 90 days; the contract says 30.
  UNSUPPORTED    nothing approved supports the promise at all.
  EXPIRING       supported today, but the supporting evidence expires before the
                 commitment date it has to survive.
  SUPPORTED      an approved, in-force source backs it, and is cited.
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .drafter import make_drafter
from .evidence import EvidenceStore
from .gates import post_gate, pre_gate
from .models import Draft, Question
from .report import CSS
from .retrieve import Retriever
from .tenants import Tenant, foreign_parties, load_tenant

CONTRADICTED = "CONTRADICTED"
UNSUPPORTED = "UNSUPPORTED"
EXPIRING = "EXPIRING"
SUPPORTED = "SUPPORTED"

SEVERITY = {CONTRADICTED: 0, UNSUPPORTED: 1, EXPIRING: 2, SUPPORTED: 3}
CHIP = {CONTRADICTED: "c-bad", UNSUPPORTED: "c-warn", EXPIRING: "c-rev", SUPPORTED: "c-ok"}


@dataclass
class CommitmentFinding:
    commitment_id: str
    instrument: str
    counterparty: str
    text: str
    owner: str
    due_date: str | None
    verdict: str
    detail: str
    citations: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"commitment_id": self.commitment_id, "instrument": self.instrument,
                "counterparty": self.counterparty, "text": self.text, "owner": self.owner,
                "due_date": self.due_date, "verdict": self.verdict,
                "detail": self.detail, "citations": self.citations}


@dataclass
class RegisterResult:
    tenant: Tenant
    generated: date
    findings: list[CommitmentFinding]

    def count(self, verdict: str) -> int:
        return sum(1 for f in self.findings if f.verdict == verdict)

    @property
    def at_risk(self) -> int:
        return sum(1 for f in self.findings if f.verdict != SUPPORTED)

    def to_dict(self) -> dict:
        return {"tenant": self.tenant.slug, "generated": self.generated.isoformat(),
                "commitments": len(self.findings), "at_risk": self.at_risk,
                "by_verdict": {v: self.count(v)
                               for v in (CONTRADICTED, UNSUPPORTED, EXPIRING, SUPPORTED)},
                "findings": [f.to_dict() for f in self.findings]}


def _assertion_check(store: EvidenceStore, key: str, promised: str) -> tuple[bool, str] | None:
    """Compare a promise against every approved source that declares this key."""
    declaring = [s for s in store.sources.values() if s.is_approved() and key in s.assertions]
    if not declaring:
        return None
    values = {s.assertions[key] for s in declaring}
    if promised in values and len(values) == 1:
        return True, f"{key} = {promised} in {declaring[0].source_id}"
    stated = "; ".join(f"{s.source_id} says {s.assertions[key]}" for s in declaring)
    return False, f"contract promises {key} = {promised}, but {stated}"


def evaluate(tenant_slug: str, evidence_root: Path, register_path: Path,
             today: date | None = None, drafter_kind: str = "mock") -> RegisterResult:
    today = today or date.today()
    tenant = load_tenant(evidence_root, tenant_slug)
    store = EvidenceStore(tenant_slug, evidence_root)
    retriever = Retriever(store)
    drafter = make_drafter(drafter_kind, retriever)
    others = foreign_parties(evidence_root, tenant_slug)
    spec = json.loads(Path(register_path).read_text(encoding="utf-8"))

    findings: list[CommitmentFinding] = []
    for c in spec["commitments"]:
        verdict, detail, citations = UNSUPPORTED, "", []

        # 1. A declared, machine-checkable assertion is the strongest signal and
        #    is checked first: a contradiction here is a fact, not an inference.
        checked = None
        if c.get("assertion_key") and c.get("promised_value"):
            checked = _assertion_check(store, c["assertion_key"], c["promised_value"])
        if checked and not checked[0]:
            verdict, detail = CONTRADICTED, checked[1]

        # 2. Otherwise ask the corpus the question the commitment implies, through
        #    the same gates a buyer's question would go through.
        if verdict != CONTRADICTED:
            q = Question(question_id=c["id"], row=0, domain="commitment",
                         text=c.get("question", c["text"]))
            d = Draft(question_id=q.question_id, answer=None)
            d = pre_gate(q, d, tenant_slug, others)
            if not d.abstained:
                d = drafter.draft(q, tenant_slug)
                d = pre_gate(q, d, tenant_slug, others)
            d = post_gate(q, d, store, today)

            if d.status.released and d.citations:
                citations = [{"source_id": x.source_id, "version": x.version,
                              "location": x.location} for x in d.citations]
                verdict = SUPPORTED
                detail = f"backed by {', '.join(x['source_id'] for x in citations)}"
                if checked and checked[0]:
                    detail += f"; {checked[1]}"
                # 3. Supported today is not the same as supported when it matters.
                due = c.get("due_date")
                if due:
                    due_date = date.fromisoformat(due)
                    expiring = [store.sources[x["source_id"]] for x in citations
                                if store.sources[x["source_id"]].expiry_date < due_date]
                    if expiring:
                        verdict = EXPIRING
                        detail = ("; ".join(
                            f"{s.source_id} expires {s.expiry_date.isoformat()}"
                            for s in expiring) + f", before the commitment date {due}")
            else:
                verdict = UNSUPPORTED
                detail = (d.gaps[0] if d.gaps
                          else "no approved evidence supports this commitment")

        findings.append(CommitmentFinding(
            commitment_id=c["id"], instrument=c["instrument"],
            counterparty=c.get("counterparty", ""), text=c["text"],
            owner=c.get("owner", ""), due_date=c.get("due_date"),
            verdict=verdict, detail=detail, citations=citations))

    findings.sort(key=lambda f: (SEVERITY[f.verdict], f.commitment_id))
    return RegisterResult(tenant=tenant, generated=today, findings=findings)


EXTRA_CSS = """
.cm{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--line);
padding:14px 18px;margin-bottom:9px}
.cm.CONTRADICTED{border-left-color:var(--bad)} .cm.UNSUPPORTED{border-left-color:var(--warn)}
.cm.EXPIRING{border-left-color:var(--rev)} .cm.SUPPORTED{border-left-color:var(--ok)}
.cm .head{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:7px}
.cm .inst{font:600 11px "IBM Plex Mono",monospace;color:var(--muted)}
.cm .txt{font-size:14px;line-height:1.55;margin-bottom:6px}
.cm .det{font:12px/1.6 "IBM Plex Mono",monospace;color:var(--muted)}
"""


def render_body(result: RegisterResult) -> str:
    esc = lambda t: html.escape(str(t), quote=False)      # noqa: E731
    blocks = []
    for f in result.findings:
        cites = (" · cites " + ", ".join(f"{c['source_id']} v{c['version']}" for c in f.citations)
                 if f.citations else "")
        due = f" · due {esc(f.due_date)}" if f.due_date else ""
        blocks.append(
            f'<div class="cm {f.verdict}"><div class="head">'
            f'<span class="chip {CHIP[f.verdict]}">{f.verdict}</span>'
            f'<span class="inst">{esc(f.instrument)} · {esc(f.counterparty)}{due}</span></div>'
            f'<div class="txt">&ldquo;{esc(f.text)}&rdquo;</div>'
            f'<div class="det">{esc(f.detail)}{esc(cites)} · owner {esc(f.owner)}</div></div>')

    return f"""<header>
<div class="eyebrow">Commitment register · generated by Pramana</div>
<h1>What sales promised, and what GRC can evidence.</h1>
<div class="runmeta">tenant={esc(result.tenant.slug)} · generated={result.generated.isoformat()}
 · {result.at_risk} of {len(result.findings)} commitments are not currently defensible</div>
</header>

<div class="grid">
<div class="stat bad"><b>{result.count(CONTRADICTED)}</b><span>contradicted</span></div>
<div class="stat warn"><b>{result.count(UNSUPPORTED)}</b><span>unsupported</span></div>
<div class="stat"><b>{result.count(EXPIRING)}</b><span>evidence expires first</span></div>
<div class="stat ok"><b>{result.count(SUPPORTED)}</b><span>supported and cited</span></div>
</div>

<div class="panel"><h3>Why this is a different question</h3><p>A questionnaire asks what you can
say. This asks whether you can stand behind what you already said. The commitments come from
executed contracts, RFP responses and DPAs; each is checked against the same evidence corpus,
through the same gates. A contradiction here is not a judgement call — a machine-checkable
assertion in an approved policy disagrees with a signed number.</p></div>

{''.join(blocks)}
"""


def write(result: RegisterResult, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path, json_path = out_dir / "index.html", out_dir / "commitments.json"
    title = html.escape(result.tenant.title, quote=False)
    html_path.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commitment register — {title}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}{EXTRA_CSS}</style></head><body><div class="wrap">
{render_body(result)}
<footer>Generated by Pramana on {result.generated.isoformat()} from {title}'s commitment
register and approved evidence corpus.</footer>
</div></body></html>""", encoding="utf-8")
    json_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return html_path, json_path
