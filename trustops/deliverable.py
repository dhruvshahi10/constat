"""The client deliverable package — what an engagement actually hands over.

Pramana is operated as a service. The client does not run the engine; they
receive its output, and that output is the thing they pay for. A run directory
is an operator's workspace: correct, but not a deliverable. This module turns
one run into a single dated folder that survives being emailed on its own —
a cover page, the completed workbook, the audit working paper, the trust page,
the commitment register, the machine-readable contracts and the tamper-evident
log, and the artifact the client actually works from: `evidence_gaps.md`.

Two rules govern every word written here, because a client reads it:

  A refusal is the control working. The engine refuses when it has nothing it
  is permitted to cite. That is the product, so refusals are reported as a
  number in their own right and explained, never buried as a failure rate.

  Nothing is overstated. Each open item names the document that must be
  produced, renewed or reconciled and who it was routed to. Where a fact is not
  available — the corpus has moved, the log is unsigned — the package says so
  instead of implying otherwise.

If the run was reviewed (`review.json`), the package reflects the reviewer's
decisions: the session replays them onto the drafts before anything is counted,
so the cover page states the delivered position rather than the draft one.
"""
from __future__ import annotations

import html
import json
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import quote

from . import commitments as commitments_mod
from . import trustpage as trustpage_mod
from .evidence import EvidenceStore
from .models import AnswerStatus, Draft, QState, Question
from .pipeline import AuditLog
from .report import CSS
from .review import ReviewError, ReviewSession
from .tenants import Tenant, load_tenant

REPO_ROOT = Path(__file__).resolve().parents[1]


class DeliveryError(RuntimeError):
    """The run cannot be packaged — always says what is missing and what to run."""


# --- the work-list -----------------------------------------------------------
# Groups are ordered by how much trouble they are, which is also the order a
# client should work them: a contradiction is already-published disagreement,
# an expired document is a claim that used to be true, a missing one is a claim
# that was never made.
GROUPS: list[tuple[str, str, str]] = [
    ("contradiction", "Two approved documents disagree",
     "Both are approved and in force, and they say different things about the same "
     "machine-checked value. Until they agree, neither can be cited — publishing "
     "either one would contradict a document your own company also stands behind."),
    ("stale", "The supporting document has expired",
     "The document exists and was approved, but its own expiry date has passed. An "
     "expired document cannot support a present-tense claim about how you operate today."),
    ("certificate", "Certification claimed, no certificate on file",
     "The question asks whether you hold a certification. Nothing of certificate or "
     "attestation class was found, and certification is never inferred from a policy, "
     "a plan or a roadmap that mentions the same scheme."),
    ("no_evidence", "No approved document covers this",
     "Nothing in your approved corpus addresses the question, so no answer was written. "
     "This is the largest and most fixable group: each one is a document that does not "
     "exist yet, or exists but has never been approved into the corpus."),
    ("legal", "Needs legal, not evidence",
     "The question asks for a contractual or liability commitment. That is a decision "
     "counsel makes, not a fact evidence can establish, so it was routed before any "
     "answer was drafted."),
    ("scope", "Asked about someone else",
     "The question names a party other than you, or asks about the answering system "
     "itself. Answering it from your evidence would attribute one company's controls "
     "to another."),
]
GROUP_TITLES = {key: title for key, title, _ in GROUPS}


@dataclass
class GapItem:
    """One refused question, expressed as a job somebody has to do."""
    question_id: str
    domain: str
    question: str
    group: str
    action: str
    documents: list[str] = field(default_factory=list)
    routed_to: str = ""
    control_note: str = ""

    def to_dict(self) -> dict:
        return {"question_id": self.question_id, "domain": self.domain,
                "question": self.question, "reason": self.group,
                "reason_label": GROUP_TITLES.get(self.group, self.group),
                "action": self.action, "documents": self.documents,
                "routed_to": self.routed_to, "control_note": self.control_note}


@dataclass
class Artifact:
    """A file in the package, described the way a non-technical reader needs it."""
    path: str            # relative to the package root
    label: str
    what: str


@dataclass
class DeliveryPackage:
    tenant: Tenant
    run_dir: Path
    out_dir: Path
    engagement_date: date
    summary: dict
    gaps: list[GapItem]
    artifacts: list[Artifact]
    notes: list[str] = field(default_factory=list)

    @property
    def index_path(self) -> Path:
        return self.out_dir / "index.html"


# --- loading -----------------------------------------------------------------
def _default_display(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _resolve_evidence_root(manifest: dict, override: Path | None) -> Path:
    if override is not None:
        return Path(override)
    recorded = Path(manifest.get("evidence_root", ""))
    if recorded.is_dir():
        return recorded
    return REPO_ROOT / "data" / "evidence"


def _flag_values(draft: Draft, prefix: str) -> list[str]:
    """Source ids carried structurally on the gate flags, not parsed out of prose."""
    out: list[str] = []
    for flag in draft.gate_flags:
        if flag.startswith(prefix + ":"):
            value = flag.split(":", 1)[1].strip()
            if value and value not in out:
                out.append(value)
    return out


def _classify(draft: Draft) -> str:
    if draft.route == "LEGAL":
        return "legal"
    if _flag_values(draft, "OUT_OF_SCOPE_PARTY"):
        return "scope"
    if _flag_values(draft, "CONTRADICTION") or (draft.route or "").startswith("SOURCE_OWNER"):
        return "contradiction"
    if _flag_values(draft, "STALE_EVIDENCE"):
        return "stale"
    # A refused certification question is its own kind of gap whether the gate
    # rejected a policy of the same scheme or found nothing at all: in both
    # cases the missing document is the certificate itself, and saying "produce
    # a document covering this domain" would send the client after the wrong one.
    if _flag_values(draft, "CERT_INFERENCE_BLOCKED") or \
            any(f.startswith("CERT_CLAIM") for f in draft.gate_flags):
        return "certificate"
    return "no_evidence"


def _route_label(draft: Draft, domain: str) -> str:
    route = draft.route or ""
    if route == "LEGAL":
        return "Your legal / contracts owner"
    if route.startswith("SOURCE_OWNER:"):
        owners = [o.strip() for o in route.split(":", 1)[1].split(",") if o.strip()]
        return ("The owners of the conflicting documents — " + ", ".join(owners)
                if owners else "The owners of the conflicting documents")
    if route == "SME":
        return f"Your subject-matter expert for {domain}"
    return route or "Your security owner"


def _describe_source(store: EvidenceStore | None, source_id: str, suffix: str = "") -> str:
    """Name a document the way its owner would recognise it."""
    src = store.sources.get(source_id) if store else None
    if src is None:
        return f"{source_id}{suffix}"
    parts = [f"{source_id} — {src.title} (v{src.version}"]
    parts.append(f", owner {src.owner})" if src.owner else ")")
    return "".join(parts) + suffix


def _gap_items(questions: list[Question], drafts: dict[str, Draft],
               store: EvidenceStore | None, client: str) -> list[GapItem]:
    order = {key: i for i, (key, _, _) in enumerate(GROUPS)}
    items: list[GapItem] = []
    for q in questions:
        d = drafts[q.question_id]
        if d.status.released:
            continue                      # something left the system; not a refusal
        group = _classify(d)
        documents: list[str] = []
        action = ""

        if group == "contradiction":
            ids = _flag_values(d, "CONTRADICTION")
            documents = [_describe_source(store, sid) for sid in ids]
            for sid in _flag_values(d, "STALE_EVIDENCE"):
                src = store.sources.get(sid) if store else None
                expiry = f", expired {src.expiry_date.isoformat()}" if src else ""
                documents.append(_describe_source(
                    store, sid, expiry + " — also out of date"))
            named = " and ".join(ids) if ids else "the conflicting documents"
            action = (f"Decide which value is correct, correct and re-approve the document "
                      f"that is wrong, so {named} agree. Both are approved today, which is "
                      f"why neither can be cited.")
        elif group == "stale":
            ids = _flag_values(d, "STALE_EVIDENCE")
            for sid in ids:
                src = store.sources.get(sid) if store else None
                expiry = f", expired {src.expiry_date.isoformat()}" if src else ""
                documents.append(_describe_source(store, sid, expiry))
            named = " and ".join(ids) if ids else "the supporting document"
            action = (f"Re-run or re-issue the underlying work, then approve the new version "
                      f"of {named} into the corpus. Extending a date on an expired document "
                      f"without redoing the work would make the claim false rather than stale.")
        elif group == "certificate":
            ids = _flag_values(d, "CERT_INFERENCE_BLOCKED")
            for sid in ids:
                src = store.sources.get(sid) if store else None
                kind = f" — currently a {src.type}, not a certificate" if src else ""
                documents.append(_describe_source(store, sid, kind))
            action = ("Supply the certificate or attestation report itself — the signed "
                      "auditor deliverable, with its scope and validity dates. If the "
                      "certification is not yet held, the honest answer to this question is "
                      "the roadmap, given by a person, not by the engine.")
        elif group == "legal":
            action = ("Counsel answers this in the contract, not the questionnaire. Nothing "
                      "was drafted, and nothing should be answered from evidence.")
        elif group == "scope":
            party = (_flag_values(d, "OUT_OF_SCOPE_PARTY") or ["another party"])[0]
            subject = ("this answering system's own configuration"
                       if party == "SYSTEM_CONFIGURATION" else party)
            action = (f"Go back to whoever sent the questionnaire: this question is about "
                      f"{subject}, not {client}. It was refused rather than answered from "
                      f"{client}'s evidence.")
        else:
            action = (f"Produce an approved document covering {q.domain} that answers this "
                      f"question, and add it to {client}'s corpus. Nothing approved today "
                      f"addresses it, so no answer was written.")

        control_note = next((g for g in d.gaps if g.strip()), "")
        items.append(GapItem(
            question_id=q.question_id, domain=q.domain,
            question=" ".join(q.text.split()), group=group, action=action,
            documents=documents, routed_to=_route_label(d, q.domain),
            control_note=" ".join(control_note.split())))

    items.sort(key=lambda i: (order.get(i.group, 99), i.question_id))
    return items


def _partial_items(questions: list[Question], drafts: dict[str, Draft]) -> list[GapItem]:
    """Answers that WERE released but carry a recorded caveat.

    Not refusals, and deliberately kept out of the refusal count — but a client
    fixing their corpus wants them, because each one is an answer that would be
    stronger with one more document.
    """
    out: list[GapItem] = []
    for q in questions:
        d = drafts[q.question_id]
        if not d.status.released or not d.gaps:
            continue
        out.append(GapItem(
            question_id=q.question_id, domain=q.domain,
            question=" ".join(q.text.split()), group="partial",
            action="An answer was released and cited; the note below records what was "
                   "rejected alongside it.",
            routed_to=_route_label(d, q.domain),
            control_note=" ".join(" ".join(d.gaps[:2]).split())))
    return out


# --- summary -----------------------------------------------------------------
def _summarise(questions: list[Question], drafts: dict[str, Draft], manifest: dict,
               metrics: dict, chain_valid: bool, chain_signed: bool,
               decisions: list[dict], gaps: list[GapItem]) -> dict:
    total = len(questions)
    released = [d for d in drafts.values() if d.status.released]
    human_authored = [d for d in released if d.status is AnswerStatus.HUMAN_AUTHORED]
    cited = [d for d in released
             if d.citations and d.status is not AnswerStatus.HUMAN_AUTHORED]
    refused = [d for d in drafts.values() if not d.status.released]
    citations = sum(len(d.citations) for d in cited)
    by_group: dict[str, int] = {}
    for item in gaps:
        by_group[item.group] = by_group.get(item.group, 0) + 1
    return {
        "questions": total,
        "answered_with_citations": len(cited),
        "citations_released": citations,
        "human_authored": len(human_authored),
        "refused": len(refused),
        "open_items": len(gaps),
        "open_items_by_reason": by_group,
        "signed_off": sum(1 for q in questions if q.state == QState.DELIVERED),
        "awaiting_sign_off": sum(1 for q in questions if q.state == QState.GRC_REVIEW),
        "human_decisions": len(decisions),
        "reviewers": sorted({d.get("actor", "") for d in decisions if d.get("actor")}),
        "reviewer_mode": manifest.get("reviewer_mode", metrics.get("reviewer_mode", "unknown")),
        "drafter": manifest.get("drafter", metrics.get("drafter", "unknown")),
        "audit_chain_valid": chain_valid,
        "audit_chain_signed": chain_signed,
        "audit_events": metrics.get("audit_events"),
        "run": Path(manifest.get("_run_dir", "")).name,
    }


def _chain_sentence(summary: dict) -> str:
    if not summary["audit_chain_valid"]:
        return ("The audit log in this package does NOT verify. Do not rely on it, and "
                "ask your Pramana operator to re-issue the package before you use any "
                "of it in an audit.")
    strength = ("Each event is also signed, so the log cannot be regenerated wholesale "
                "without the operator's key."
                if summary["audit_chain_signed"] else
                "The log is tamper-evident: an edit to any past line breaks the chain "
                "from that point on. It is not signed, so it evidences that history was "
                "not edited, not that it could not have been rewritten from scratch.")
    return ("The audit log covering this engagement verifies intact. Every step — receipt "
            "of your questionnaire, classification, drafting, each gate decision, every "
            "approval and the final export — is recorded and hash-chained. " + strength)


def _summary_paragraphs(pkg_summary: dict, client: str, workbook: str,
                        trust: dict | None, register: dict | None) -> list[str]:
    s = pkg_summary
    paras: list[str] = []
    paras.append(
        f"Of the {s['questions']} questions in {workbook}, {s['answered_with_citations']} "
        f"were answered from {client}'s own approved evidence. Each of those answers "
        f"carries the document, version and location it came from — "
        f"{s['citations_released']} citations in total — so a buyer's security team can "
        f"check any answer against the source rather than take it on trust.")
    if s["refused"]:
        paras.append(
            f"{s['refused']} questions were refused. The engine found nothing it was "
            f"permitted to cite, so it wrote nothing. That is the control working, not a "
            f"shortfall: an unsupported answer on a security questionnaire is a statement "
            f"{client} would have to stand behind later, and the engine is built so it "
            f"cannot produce one.")
    else:
        paras.append(
            "No question was refused: every question in this workbook was supported by "
            "approved, in-force evidence.")
    if s["open_items"]:
        paras.append(
            f"Those {s['open_items']} refusals are your work-list, set out in "
            f"evidence_gaps.md. Each one names the document that has to be produced, "
            f"renewed or reconciled and who it was routed to. Close them and the same "
            f"questions answer themselves from evidence next time.")
    if s["human_authored"]:
        paras.append(
            f"{s['human_authored']} answers were written by a named person on your side "
            f"rather than derived from evidence. They are labelled HUMAN AUTHORED in the "
            f"workbook and in contracts.json, so nobody later mistakes them for "
            f"evidence-backed answers.")
    if s["human_decisions"]:
        who = ", ".join(s["reviewers"]) or "a named reviewer"
        paras.append(
            f"{s['human_decisions']} answers carry a recorded human decision by {who}. "
            f"Those decisions are on the same audit chain as the run they decided on.")
    elif s["awaiting_sign_off"]:
        paras.append(
            f"{s['awaiting_sign_off']} answers are cited and clean but still await a named "
            f"reviewer's sign-off. They are marked as such in the working paper; they are "
            f"not represented as approved.")
    if trust:
        paras.append(
            f"Your trust page answers {trust['self_serve_answers']} of the "
            f"{trust['questions']} questions buyers most commonly ask, without anyone at "
            f"{client} being asked. The remaining {trust['open_items']} are shown as open "
            f"items a buyer must request, because publishing an answer that is not fully "
            f"evidence-backed is how a trust page starts lying.")
    if register:
        paras.append(
            f"The commitment register checks {register['commitments']} promises already "
            f"made in contracts and RFP responses against the same evidence. "
            f"{register['at_risk']} of them cannot currently be stood behind.")
    paras.append(_chain_sentence(s))
    return paras


# --- writing -----------------------------------------------------------------
def _md_escape(text: str) -> str:
    return " ".join(str(text).split())


def write_evidence_gaps(path: Path, client: str, engagement: date, summary: dict,
                        gaps: list[GapItem], partials: list[GapItem], run_name: str) -> Path:
    lines: list[str] = []
    lines.append(f"# Evidence gaps — {_md_escape(client)}")
    lines.append("")
    lines.append(f"Engagement date: {engagement.isoformat()}  ")
    lines.append(f"Prepared by Pramana from run `{_md_escape(run_name)}`")
    lines.append("")
    lines.append(
        f"{summary['answered_with_citations']} of {summary['questions']} questions were "
        f"answered from approved evidence and cited. {summary['refused']} were refused: "
        f"the engine had nothing it was allowed to cite, so it wrote nothing.")
    lines.append("")
    lines.append(
        "This file is the list of what has to exist before those questions can be answered "
        "from evidence. Each item names the document to produce, renew or reconcile and "
        "who it was routed to. Nothing here requires Pramana to fix — it requires a "
        "document.")
    lines.append("")

    if not gaps:
        lines.append("**No open items.** Every question in this engagement was answered "
                     "from approved, in-force evidence.")
    else:
        lines.append("## Summary")
        lines.append("")
        lines.append("| Reason | Questions |")
        lines.append("| --- | ---: |")
        for key, title, _ in GROUPS:
            count = summary["open_items_by_reason"].get(key, 0)
            if count:
                lines.append(f"| {title} | {count} |")
        lines.append(f"| **Total open items** | **{len(gaps)}** |")
        lines.append("")

        for key, title, why in GROUPS:
            group_items = [g for g in gaps if g.group == key]
            if not group_items:
                continue
            noun = "question" if len(group_items) == 1 else "questions"
            lines.append(f"## {title} — {len(group_items)} {noun}")
            lines.append("")
            lines.append(_md_escape(why))
            lines.append("")
            for item in group_items:
                lines.append(f"### {item.question_id} · {_md_escape(item.domain)}")
                lines.append("")
                lines.append(f"**Question asked:** {_md_escape(item.question)}")
                lines.append("")
                lines.append(f"- **What has to happen:** {_md_escape(item.action)}")
                if item.documents:
                    lines.append("- **Document(s):**")
                    for doc in item.documents:
                        lines.append(f"    - {_md_escape(doc)}")
                else:
                    lines.append("- **Document(s):** none on file — this is the gap.")
                lines.append(f"- **Routed to:** {_md_escape(item.routed_to)}")
                if item.control_note:
                    lines.append(f"- **What the control recorded:** {_md_escape(item.control_note)}")
                lines.append("")

    if partials:
        lines.append("## Answered, with a note on file")
        lines.append("")
        lines.append(
            "These were answered and cited — they are not refusals and are not counted "
            "above. Each one released an answer while rejecting something alongside it, "
            "so closing the note makes an answer that already ships a stronger one.")
        lines.append("")
        for item in partials:
            lines.append(f"- **{item.question_id}** · {_md_escape(item.domain)} — "
                         f"{_md_escape(item.control_note)}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Every refusal above is recorded in the audit log shipped with this package, with "
        "the gate that made it and the timestamp. A refusal is not a missing answer — it "
        "is the system declining to make a claim it cannot support.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


README_INTRO = """\
This is the complete output of your Pramana engagement. It is self-contained:
every file below is in this folder, and nothing here needs an internet
connection or an account to open.

**Start with `index.html`.** Open it in any browser. It has the headline
numbers and a link to everything else.

One idea explains the whole package: an answer is released only when an
approved, in-force document supports it, and that document is named next to the
answer. When no such document exists, the engine refuses and says why. A
refusal is the control working — it is the reason the answers you can ship are
worth shipping.

## The files
"""

README_TAIL = """\

## How to read a refusal

A refused question has no answer text. It has a reason, a named document that
has to exist, and a person it was routed to. Refusals are not failures of the
engine; they are the questions where answering from your current evidence would
have meant asserting something you could not support.

Work `evidence_gaps.md` from the top: contradictions first (two approved
documents disagreeing is a live problem regardless of this questionnaire), then
expired documents, then the ones that were never written.

## Questions

Ask your Pramana operator. If something in this package looks wrong, say so
before you send the workbook on — the whole point of the audit log is that the
record can be checked rather than argued about.
"""


def write_readme(path: Path, client: str, engagement: date, summary: dict,
                 artifacts: list[Artifact], notes: list[str]) -> Path:
    lines = [f"# {client} — security questionnaire response", "",
             f"Engagement date: {engagement.isoformat()}", "",
             README_INTRO]
    for art in artifacts:
        lines.append(f"### `{art.path}`")
        lines.append(f"**{art.label}** — {_md_escape(art.what)}")
        lines.append("")
    lines.append("## The numbers on the cover page")
    lines.append("")
    lines.append(f"- **{summary['answered_with_citations']} answered with citations** — "
                 f"answers released with the document, version and location behind them.")
    lines.append(f"- **{summary['refused']} refused** — no approved, in-force document "
                 f"supported an answer, so none was written.")
    lines.append(f"- **{summary['open_items']} open items** — the refusals, restated as "
                 f"documents somebody has to produce. This is `evidence_gaps.md`.")
    lines.append(f"- **Audit chain** — "
                 f"{'verifies intact' if summary['audit_chain_valid'] else 'DOES NOT VERIFY'}"
                 f"{'; signed' if summary['audit_chain_signed'] else '; unsigned (tamper-evident, not tamper-proof)'}.")
    lines.append("")
    if notes:
        lines.append("## Notes on this package")
        lines.append("")
        for note in notes:
            lines.append(f"- {_md_escape(note)}")
        lines.append("")
    lines.append(README_TAIL)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


EXTRA_CSS = """
.lede{font-size:16.5px;line-height:1.65;max-width:74ch;margin-bottom:14px}
.lede.first{font-size:18px}
.files{margin-top:6px}
.file{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--ok);
padding:14px 18px;margin-bottom:9px}
.file a{color:var(--ink);text-decoration:none;font-weight:600;font-size:15px;
border-bottom:1.5px solid var(--ok)}
.file a:hover{color:var(--ok)}
.file .path{font:11.5px "IBM Plex Mono",monospace;color:var(--muted);margin-top:3px}
.file .what{font-size:13.5px;color:var(--ink);margin-top:7px;max-width:74ch}
.file.work{border-left-color:var(--warn)}
.file.work a{border-bottom-color:var(--warn)}
.note{background:var(--warnbg);border:1px solid var(--warn);padding:12px 16px;
font-size:13px;margin-top:12px}
.reasons{margin-top:10px}
"""


def _link(art: Artifact, work: bool = False) -> str:
    href = "/".join(quote(part) for part in art.path.split("/"))
    return (f'<div class="file{" work" if work else ""}">'
            f'<a href="{html.escape(href, quote=True)}">{html.escape(art.label)}</a>'
            f'<div class="path">{html.escape(art.path)}</div>'
            f'<div class="what">{html.escape(art.what)}</div></div>')


def write_index(path: Path, client: str, engagement: date, summary: dict,
                artifacts: list[Artifact], gaps: list[GapItem],
                paragraphs: list[str], generated: date) -> Path:
    stats = [
        ("ok", summary["answered_with_citations"], "Answered with citations"),
        ("warn", summary["refused"], "Refused — nothing citable"),
        ("warn", summary["open_items"], "Open items for you"),
        ("ok" if summary["audit_chain_valid"] else "bad",
         "VALID" if summary["audit_chain_valid"] else "BROKEN", "Audit chain"),
    ]
    stat_html = "".join(
        f'<div class="stat {cls}"><b>{html.escape(str(value))}</b>'
        f'<span>{html.escape(label)}</span></div>' for cls, value, label in stats)

    lede = "".join(
        f'<p class="lede{" first" if i == 0 else ""}">{html.escape(p)}</p>'
        for i, p in enumerate(paragraphs))

    reason_rows = ""
    if gaps:
        rows = "".join(
            f"<tr><td>{html.escape(title)}</td><td>{summary['open_items_by_reason'][key]}</td></tr>"
            for key, title, _ in GROUPS if summary["open_items_by_reason"].get(key))
        reason_rows = (
            '<h2>What the open items are</h2>'
            '<p class="sub">Every refused question, grouped by why the answer could not be '
            'released. The full list — with the document to produce and who owns it — is in '
            'evidence_gaps.md.</p>'
            f'<table class="reasons"><tr><th>Reason</th><th>Questions</th></tr>{rows}</table>')

    work_paths = {"evidence_gaps.md"}
    files_html = "".join(_link(a, work=a.path in work_paths) for a in artifacts)

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(client)} — Pramana engagement package</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}{EXTRA_CSS}</style></head><body><div class="wrap">
<header>
<div class="eyebrow">Pramana · Engagement package</div>
<h1>{html.escape(client)} — security questionnaire response</h1>
<div class="runmeta">engagement date {engagement.isoformat()} ·
package generated {generated.isoformat()} · questions {summary['questions']} ·
audit chain {'VALID' if summary['audit_chain_valid'] else 'BROKEN'}</div>
</header>

<div class="grid">{stat_html}</div>

<h2>What was done</h2>
{lede}

{reason_rows}

<h2>Everything in this package</h2>
<p class="sub">All files are in this folder. Nothing below needs an account or an internet
connection to open.</p>
<div class="files">{files_html}</div>

<footer>Prepared by Pramana for {html.escape(client)} · engagement date
{engagement.isoformat()} · package generated {generated.isoformat()}.<br>
Every released answer names the approved document behind it. Every refusal names what is
missing. Both are recorded in the audit log shipped with this package.</footer>
</div></body></html>"""
    path.write_text(page, encoding="utf-8")
    return path


# --- assembly ----------------------------------------------------------------
def build(run_dir: Path, out_root: Path | None = None, out_dir: Path | None = None,
          drafter_kind: str = "mock", evidence_root: Path | None = None,
          commitments_dir: Path | None = None,
          generated: date | None = None) -> DeliveryPackage:
    """Assemble one run into a client-ready folder and return what was written."""
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise DeliveryError(
            f"{run_dir} has no manifest.json, so it is not a packageable run. "
            f"Re-run the questionnaire to regenerate it.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["_run_dir"] = str(run_dir)

    tenant_slug = manifest["tenant"]
    engagement = (date.fromisoformat(manifest["run_date"])
                  if manifest.get("run_date") else date.today())
    generated = generated or date.today()
    evidence_root = _resolve_evidence_root(manifest, evidence_root)
    try:
        tenant = load_tenant(evidence_root, tenant_slug)
    except FileNotFoundError:
        tenant = Tenant(slug=tenant_slug, display_name=_default_display(tenant_slug))
    client = tenant.title

    try:
        session = ReviewSession(run_dir)      # replays review.json, if any
    except ReviewError as exc:
        raise DeliveryError(str(exc)) from exc

    out_dir = Path(out_dir) if out_dir else \
        Path(out_root or "deliveries") / f"{engagement.isoformat()}-{tenant_slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    artifacts: list[Artifact] = []

    # 1. the completed workbook, exactly as the run (and any review) exported it
    delivered = sorted(run_dir.glob("*__DELIVERED.*"))
    if not delivered:
        raise DeliveryError(
            f"no completed workbook (*__DELIVERED.*) in {run_dir}. Re-run, or run "
            f"`python review.py export --run {run_dir}` if a review is in progress.")
    workbook = delivered[0]
    shutil.copy2(workbook, out_dir / workbook.name)
    artifacts.append(Artifact(
        workbook.name, "Your completed questionnaire",
        "The workbook you were sent, returned with the answers filled in. Row order, "
        "question wording and every original tab are unchanged — only the answer columns "
        "were written. This is the file you send back."))

    # 2. the working paper
    report_src = run_dir / "run_report.html"
    if report_src.is_file():
        shutil.copy2(report_src, out_dir / "run_report.html")
        artifacts.append(Artifact(
            "run_report.html", "Audit working paper",
            "Every question with its answer, the documents cited underneath it, and the "
            "gate decision that released or refused it. This is what you hand an auditor "
            "or a buyer who asks how an answer was reached."))
    else:
        notes.append("The run directory has no run_report.html, so the audit working paper "
                     "is not in this package.")

    # 3. machine-readable answers — post-review, so they are the delivered position
    contracts_path = out_dir / "contracts.json"
    contracts_path.write_text(
        json.dumps({qid: d.to_contract() for qid, d in session.drafts.items()},
                   indent=2, ensure_ascii=False), encoding="utf-8")

    # 4. the audit log, verified after the copy — the copy is what you are given
    shutil.copy2(run_dir / "audit_log.jsonl", out_dir / "audit_log.jsonl")
    chain_valid = AuditLog.verify_chain(out_dir / "audit_log.jsonl")
    chain_signed = AuditLog.signed(out_dir / "audit_log.jsonl")

    decisions: list[dict] = []
    review_src = run_dir / "review.json"
    if review_src.is_file():
        raw = json.loads(review_src.read_text(encoding="utf-8"))
        decisions = raw.get("decisions", [])
        shutil.copy2(review_src, out_dir / "review_decisions.json")
        if workbook.stat().st_mtime < review_src.stat().st_mtime:
            notes.append(
                "The workbook in this package was exported before the most recent review "
                "decision. Ask your operator to re-export it.")

    # 5. trust page
    trust_summary: dict | None = None
    if (Path(evidence_root) / tenant_slug).is_dir():
        result = trustpage_mod.generate(tenant_slug, evidence_root, today=engagement,
                                        drafter_kind=drafter_kind)
        trustpage_mod.write(result, out_dir / "trust_page",
                            contact=tenant.trust_page.contact_email)
        trust_summary = result.to_dict()
        artifacts.append(Artifact(
            "trust_page/index.html", "Your trust page",
            f"A publishable page answering the {trust_summary['questions']} questions buyers "
            f"ask most often. Only the {trust_summary['self_serve_answers']} that are fully "
            f"evidence-backed are answered; the rest are shown as open items a buyer must "
            f"request. Host it, or send it as a file. The same answers as data are in "
            f"trust_page/deflection.json."))
    else:
        notes.append(f"The evidence corpus for '{tenant_slug}' was not found at "
                     f"{evidence_root}, so the trust page was not regenerated.")

    # 6. commitment register, only when the client has one
    register_summary: dict | None = None
    commitments_dir = Path(commitments_dir) if commitments_dir else \
        Path(evidence_root).parent / "commitments"
    register_spec = commitments_dir / f"{tenant_slug}.json"
    if register_spec.is_file() and (Path(evidence_root) / tenant_slug).is_dir():
        reg = commitments_mod.evaluate(tenant_slug, evidence_root, register_spec,
                                       today=engagement, drafter_kind=drafter_kind)
        commitments_mod.write(reg, out_dir / "commitment_register")
        register_summary = reg.to_dict()
        artifacts.append(Artifact(
            "commitment_register/index.html", "Commitment register",
            f"The security promises already made in your contracts and RFP responses, "
            f"checked against the same evidence. {register_summary['at_risk']} of "
            f"{register_summary['commitments']} cannot currently be stood behind — "
            f"contradicted, unsupported, or resting on evidence that expires first. The "
            f"findings as data are in commitment_register/commitments.json."))

    # 7. the work-list
    store: EvidenceStore | None = None
    if (Path(evidence_root) / tenant_slug).is_dir():
        store = EvidenceStore(tenant_slug, evidence_root)
    gaps = _gap_items(session.questions, session.drafts, store, client)
    partials = _partial_items(session.questions, session.drafts)

    metrics_path = run_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) \
        if metrics_path.is_file() else {}
    summary = _summarise(session.questions, session.drafts, manifest, metrics,
                         chain_valid, chain_signed, decisions, gaps)

    write_evidence_gaps(out_dir / "evidence_gaps.md", client, engagement, summary,
                        gaps, partials, run_dir.name)
    artifacts.append(Artifact(
        "evidence_gaps.md", "Your work-list — the evidence gaps",
        f"The {summary['open_items']} questions that could not be answered, grouped by "
        f"reason, each naming the document to produce, renew or reconcile and who it was "
        f"routed to. Close these and the same questions answer themselves next time."))

    artifacts.append(Artifact(
        "contracts.json", "Machine-readable answers",
        "Every answer as structured data — the citations behind it, its evidence status, "
        "and any recorded gap. For loading into your own GRC tooling."
        + (" It reflects the review decisions recorded in this engagement."
           if decisions else "")))
    artifacts.append(Artifact(
        "audit_log.jsonl", "Tamper-evident audit log",
        "One line per step, each carrying the hash of the line before it. Editing any past "
        "line breaks the chain from that point on, which is what makes the record checkable "
        "rather than merely stored."))
    if decisions:
        artifacts.append(Artifact(
            "review_decisions.json", "Human review decisions",
            f"The {len(decisions)} decisions a named reviewer recorded on this run — who "
            f"decided what, when, and what the answer was before and after."))
    artifacts.append(Artifact(
        "README.md", "This package, explained",
        "A plain-English description of every file here and how to read a refusal."))

    paragraphs = _summary_paragraphs(
        summary, client, workbook.name.replace("__DELIVERED", ""),
        trust_summary, register_summary)

    write_index(out_dir / "index.html", client, engagement, summary, artifacts,
                gaps, paragraphs, generated)
    write_readme(out_dir / "README.md", client, engagement, summary, artifacts, notes)

    return DeliveryPackage(tenant=tenant, run_dir=run_dir, out_dir=out_dir,
                           engagement_date=engagement, summary=summary, gaps=gaps,
                           artifacts=artifacts, notes=notes)
