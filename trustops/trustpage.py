"""Trust page generator — the deflection half of the product.

A questionnaire that never arrives costs nothing to answer. Given a tenant's
evidence corpus, this runs the standard buyer question set through the same
pipeline a real questionnaire uses and publishes the subset that is
evidence-backed, each with its provenance.

What is NOT published is the point. A question whose answer is partial, needs
human sign-off, was refused, or was routed to counsel does not appear as an
answer; it appears as an open item a buyer must request through security
review. A trust page that answers everything is a trust page nobody should
believe, and generating one from a thin corpus would be the single easiest way
for this product to start lying.

The deflection rate — evidence-backed answers over the standard set — is the
number a buyer's security team actually feels, and it is measured here rather
than asserted.
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .drafter import make_drafter
from .evidence import EvidenceStore
from .gates import post_gate, pre_gate
from .models import AnswerStatus, Draft, Question
from .report import CSS
from .retrieve import Retriever
from .tenants import Tenant, foreign_parties, load_tenant

DEFAULT_QUESTION_SET = Path(__file__).resolve().parents[1] / "data" / "trust_questions.json"

# Only a fully evidence-backed answer is published without a human. Everything
# else — partial, awaiting sign-off, refused, routed — is an open item.
PUBLISHABLE = (AnswerStatus.EVIDENCE_BACKED,)


@dataclass
class TrustAnswer:
    question_id: str
    domain: str
    text: str
    status: AnswerStatus
    answer: str | None
    citations: list[dict]
    gap: str | None

    @property
    def published(self) -> bool:
        return self.status in PUBLISHABLE


@dataclass
class TrustResult:
    tenant: Tenant
    generated: date
    answers: list[TrustAnswer]

    @property
    def published(self) -> list[TrustAnswer]:
        return [a for a in self.answers if a.published]

    @property
    def open_items(self) -> list[TrustAnswer]:
        return [a for a in self.answers if not a.published]

    @property
    def deflection_rate(self) -> float:
        return round(len(self.published) / len(self.answers), 3) if self.answers else 0.0

    def to_dict(self) -> dict:
        return {
            "tenant": self.tenant.slug,
            "generated": self.generated.isoformat(),
            "questions": len(self.answers),
            "self_serve_answers": len(self.published),
            "open_items": len(self.open_items),
            "deflection_rate": self.deflection_rate,
            "answers": [{
                "question_id": a.question_id, "domain": a.domain, "question": a.text,
                "status": a.status.value, "answer": a.answer, "citations": a.citations,
            } for a in self.answers],
        }


def load_question_set(path: Path | None = None) -> tuple[str, list[dict]]:
    data = json.loads(Path(path or DEFAULT_QUESTION_SET).read_text(encoding="utf-8"))
    return data.get("name", "question set"), data["questions"]


def generate(tenant_slug: str, evidence_root: Path, today: date | None = None,
             question_set: Path | None = None, drafter_kind: str = "mock") -> TrustResult:
    today = today or date.today()
    tenant = load_tenant(evidence_root, tenant_slug)
    store = EvidenceStore(tenant_slug, evidence_root)
    retriever = Retriever(store)
    drafter = make_drafter(drafter_kind, retriever)
    _, questions = load_question_set(question_set)
    others = foreign_parties(evidence_root, tenant_slug)

    answers: list[TrustAnswer] = []
    for spec in questions:
        q = Question(question_id=spec["id"], row=0, domain=spec["domain"], text=spec["text"])
        d = Draft(question_id=q.question_id, answer=None)
        d = pre_gate(q, d, tenant_slug, others)
        if not d.abstained:
            d = drafter.draft(q, tenant_slug)
            d = pre_gate(q, d, tenant_slug, others)
        d = post_gate(q, d, store, today)
        answers.append(TrustAnswer(
            question_id=q.question_id, domain=q.domain, text=q.text, status=d.status,
            answer=d.answer if d.status in PUBLISHABLE else None,
            citations=[{"source_id": c.source_id, "version": c.version,
                        "location": c.location} for c in d.citations]
            if d.status in PUBLISHABLE else [],
            gap=(d.gaps[0] if d.gaps else None)))
    return TrustResult(tenant=tenant, generated=today, answers=answers)


# --- rendering ---------------------------------------------------------------
EXTRA_CSS = """
.tc-domain{margin:30px 0 10px;font-family:"Space Grotesk",sans-serif;font-size:15px;font-weight:600}
.qa{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--ok);
padding:14px 18px;margin-bottom:9px}
.qa.open{border-left-color:var(--warn);background:var(--paper)}
.qa .q{font-weight:600;font-size:14px;margin-bottom:6px}
.qa .a{font-size:13.5px;line-height:1.6}
.qa .req{font:12px "IBM Plex Mono",monospace;color:var(--warn)}
"""


def render_body(result: TrustResult, contact: str = "") -> str:
    """The trust content itself, without a page shell — so the standalone page
    and the site can render the same output rather than two versions of it."""
    cfg = result.tenant.trust_page
    contact = contact or cfg.contact_email
    esc = lambda t: html.escape(str(t), quote=False)     # noqa: E731

    by_domain: dict[str, list[TrustAnswer]] = {}
    for a in result.answers:
        by_domain.setdefault(a.domain, []).append(a)

    blocks = []
    for domain, items in by_domain.items():
        blocks.append(f'<div class="tc-domain">{esc(domain)}</div>')
        for a in items:
            if a.published:
                prov = '<div class="prov">' + "<br>".join(
                    f"{esc(c['source_id'])} · v{esc(c['version'])} · {esc(c['location'])}"
                    for c in a.citations) + "</div>"
                blocks.append(f'<div class="qa"><div class="q">{esc(a.text)}</div>'
                              f'<div class="a">{esc(a.answer)}</div>{prov}</div>')
            else:
                blocks.append(
                    f'<div class="qa open"><div class="q">{esc(a.text)}</div>'
                    f'<div class="req">Not published — no self-serve answer is supported by '
                    f'our current evidence. Request this through security review.</div></div>')

    pct = round(result.deflection_rate * 100)
    contact_line = (f'<a class="btn primary" href="mailto:{esc(contact)}?subject='
                    f'Security%20review%20request">Request security review</a>'
                    if contact else "")
    intro = cfg.intro or (
        "Every answer below was generated from our approved evidence, and cites the "
        "document, version and paragraph it came from.")

    return f"""<header>
<div class="eyebrow">Trust center · generated by Pramana</div>
<h1>{esc(cfg.headline or f"{result.tenant.title} security answers")}</h1>
<div class="runmeta">tenant={esc(result.tenant.slug)} · generated={result.generated.isoformat()}
 · {len(result.published)} of {len(result.answers)} standard questions answered without a human</div>
</header>

<p class="sub" style="max-width:72ch">{esc(intro)}</p>

<div class="grid">
<div class="stat ok"><b>{pct}%</b><span>self-serve deflection</span></div>
<div class="stat"><b>{len(result.published)}</b><span>answered with citations</span></div>
<div class="stat warn"><b>{len(result.open_items)}</b><span>open — request via review</span></div>
<div class="stat"><b>{len(result.answers)}</b><span>standard questions</span></div>
</div>

<div class="panel"><h3>How to read this page</h3><p>An answer appears here only when every
claim in it is supported by an approved, in-force document. Questions we cannot support that
way are shown as open rather than answered with something plausible. That is the same rule
the engine applies to a customer questionnaire.</p></div>

<div class="cta" style="margin:22px 0">{contact_line}</div>

{''.join(blocks)}
"""


def render(result: TrustResult, contact: str = "") -> str:
    """Standalone page a client can host as-is."""
    title = html.escape(result.tenant.title, quote=False)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trust center — {title}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}{EXTRA_CSS}</style></head><body><div class="wrap">
{render_body(result, contact)}
<footer>
Generated by Pramana from {title}'s approved evidence corpus on
{result.generated.isoformat()}. Nothing on this page was written by hand.
</footer>
</div></body></html>"""


def write(result: TrustResult, out_dir: Path, contact: str = "") -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "index.html"
    json_path = out_dir / "deflection.json"
    html_path.write_text(render(result, contact), encoding="utf-8")
    json_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return html_path, json_path
