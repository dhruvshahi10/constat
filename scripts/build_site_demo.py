"""Build the landing page's interactive demo data from real engine output.

Runs the deterministic mock pipeline against the synthetic acme tenant and
writes site/demo/contracts.json: one contract per showcase question, exactly
what the live engine returns, so the landing demo is truthful without an API
call or a server. Rebuild whenever gates or evidence change:

    .venv/bin/python scripts/build_site_demo.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trustops.drafter import make_drafter          # noqa: E402
from trustops.evidence import EvidenceStore        # noqa: E402
from trustops.gates import post_gate, pre_gate     # noqa: E402
from trustops.models import Draft, Question        # noqa: E402
from trustops.retrieve import Retriever            # noqa: E402

# (id, label shown on the chip, question, which trap it demonstrates)
SHOWCASE = [
    ("mfa", "MFA enforcement", "Is multi-factor authentication enforced for all workforce access to production systems?", "cited"),
    ("ir", "Incident response", "Do you have a documented incident response plan, and within what timeframe are customers notified of a confirmed breach?", "cited"),
    ("soc2", "SOC 2 attestation", "Do you hold a current SOC 2 Type II attestation?", "cited"),
    ("iso", "ISO 27001 trap", "Is your organization ISO/IEC 27001 certified? Provide certificate number and expiry.", "cert"),
    ("del", "Deletion contradiction", "Within how many days of contract termination is customer data deleted?", "contradiction"),
    ("pen", "Stale pentest", "Has an independent penetration test been performed in the last 12 months?", "stale"),
    ("legal", "Unlimited liability", "Will Vendor contractually commit to unlimited liability for any breach?", "legal"),
]

FIXED_TODAY = date(2026, 8, 16)


def answer(question_text: str, store: EvidenceStore, retriever: Retriever) -> dict:
    q = Question(question_id="DEMO", row=0, domain="Demo", text=question_text)
    d = Draft(question_id="DEMO", answer=None)
    d = pre_gate(q, d)
    if d.route != "LEGAL":
        d = make_drafter("mock", retriever).draft(q, "acme")
        d = pre_gate(q, d)
    d = post_gate(q, d, store, FIXED_TODAY)

    if d.route == "LEGAL":
        verdict, tone = "ROUTED TO COUNSEL", "legal"
    elif d.abstained and any(f.startswith("CONTRADICTION") for f in d.gate_flags):
        verdict, tone = "REFUSED, SOURCES CONFLICT", "warn"
    elif d.abstained and any(f.startswith("STALE") for f in d.gate_flags):
        verdict, tone = "REFUSED, EVIDENCE EXPIRED", "warn"
    elif d.abstained and any(f.startswith(("CERT_INFERENCE_BLOCKED", "CERT_CLAIM"))
                             for f in d.gate_flags):
        verdict, tone = "REFUSED, CERT NEVER INFERRED", "warn"
    elif d.abstained:
        verdict, tone = "REFUSED, GAP NAMED", "warn"
    elif d.gaps or d.requires_human:
        # something citable survived, but a gate raised a finding on the way:
        # honest label, not "clean"
        verdict, tone = "CITED, HELD FOR HUMAN REVIEW", "rev"
    else:
        verdict, tone = "CITED, GATE CLEAN", "ok"
    return {
        "verdict": verdict, "tone": tone, "answer": d.answer,
        "citations": [f"{c.source_id} v{c.version} {c.location}" for c in d.citations],
        "gaps": d.gaps[:2], "flags": d.gate_flags[:2],
    }


def main() -> None:
    store = EvidenceStore("acme", ROOT / "data" / "evidence")
    retriever = Retriever(store)
    out = {}
    for key, label, text, trap in SHOWCASE:
        out[key] = {"label": label, "question": text, "trap": trap,
                    **answer(text, store, retriever)}
    dest = ROOT / "site" / "demo" / "contracts.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    refused = sum(1 for v in out.values() if v["tone"] != "ok")
    print(f"wrote {dest}: {len(out)} contracts, {refused} refusals")

    # assemble the final landing page: brand CSS + fonts + demo data inlined,
    # so the page is one self-contained file with zero external requests
    from trustops import brand
    template = (ROOT / "site" / "index.template.html").read_text(encoding="utf-8")
    page = template.replace("/*@CSS@*/", brand.stylesheet())
    page = page.replace("/*@DEMO@*/", json.dumps(out, ensure_ascii=False))
    (ROOT / "site" / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote site/index.html ({len(page) // 1024}KB)")


if __name__ == "__main__":
    main()
