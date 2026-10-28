"""Constat MCP server: the claim store and the gates, for agents.

Tools are tagged read or write. Read tools answer from claims and return a
verdict, never a sent answer. Write tools return a proposal that a person
approves, mirroring Atlan's own MCP write tools. Every call is logged as a
metric event with the caller, so "who asked what" is answerable.

Run:  CONSTAT_MCP_TOKEN=<bearer> python -m mcp_server.server          (stdio)
      python -m mcp_server.server --http 8020                           (streamable HTTP)
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constat.claims import Audience, Claim  # noqa: E402
from constat.claims.gates import gate  # noqa: E402
from constat.claims.match import ClaimMatcher  # noqa: E402
from constat.claims.store import SentAnswerRecord  # noqa: E402
from constat.persist import MetricEvent, ulid  # noqa: E402

try:
    from mcp.server.mcpserver import MCPServer as _Server  # mcp 2.x
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore  # mcp 1.x

from api.deps import get_claim_store, get_repo, get_settings  # noqa: E402

server = _Server("constat", instructions=(
    "Constat answers security questions from owned, expiring, exception-carrying claims. "
    "answer_question returns a verdict (ANSWER, HOLD_HUMAN or REFUSE), never sends anything. "
    "Writes are proposals until a person approves them."))

ACTOR = os.environ.get("CONSTAT_MCP_ACTOR", "mcp-client")


def _log(tool: str, **payload) -> None:
    repo = get_repo()
    repo.insert("metric_events", MetricEvent(id=ulid(), tenant=get_settings().default_tenant, kind="mcp_call",
                                             payload_json={"tool": tool, "actor": ACTOR} | payload))


@server.tool(name="search_claims", description="[read] Find claims by words. Returns id, statement, owner, audience, status, valid_until.")
def search_claims(query: str, audience: str = "nda", limit: int = 5) -> list[dict]:
    aud = Audience(audience)
    matches = ClaimMatcher(get_claim_store()).match(query, date.today(), aud, k=max(1, min(limit, 20)))
    _log("search_claims", query=query[:200], hits=len(matches))
    return [{"claim_id": m.claim.claim_id, "statement": m.claim.statement, "owner": m.claim.owner,
             "audience": m.claim.audience.value, "status": m.claim.status.value,
             "valid_until": m.claim.valid_until.isoformat(), "coverage": round(m.coverage, 2),
             "exceptions": m.claim.exceptions} for m in matches]


@server.tool(name="answer_question", description="[read] Gate a question against the claims. Returns a verdict: outcome ANSWER, HOLD_HUMAN or REFUSE, the difficulty class, flags, gaps and the route. Never sends.")
def answer_question(question: str, audience: str = "nda", domain: str = "") -> dict:
    aud = Audience(audience)
    matches = ClaimMatcher(get_claim_store()).match(question, date.today(), aud)
    v = gate(question, matches, date.today(), aud, domain=domain)
    _log("answer_question", question=question[:200], outcome=v.outcome, difficulty=v.difficulty.value)
    return v.to_dict() | {"note": "A verdict, not a sent answer. A person approves and sends."}


@server.tool(name="list_refusals", description="[read] Claims that cannot support answers right now (draft, expired, deprecated) grouped by owner, so owners can be asked once.")
def list_refusals(expiring_days: int = 30) -> dict:
    d = get_claim_store().freshness_digest(date.today(), expiring_days)
    _log("list_refusals", owners=len(d))
    return {"as_of": date.today().isoformat(), "by_owner": d}


@server.tool(name="claim_freshness", description="[read] One claim's status, validity, evidence refs and version hash.")
def claim_freshness(claim_id: str) -> dict:
    c = get_claim_store().get(claim_id)
    _log("claim_freshness", claim_id=claim_id, found=c is not None)
    if c is None:
        return {"error": f"no claim {claim_id}"}
    ok, why = c.is_usable(date.today(), Audience.INTERNAL)
    return {"claim_id": c.claim_id, "status": c.status.value, "usable": ok, "unusable_reason": why,
            "valid_until": c.valid_until.isoformat(), "owner": c.owner, "version_hash": c.version_hash(),
            "evidence_refs": [{"kind": e.kind, "ref": e.ref, "checked_on": e.checked_on.isoformat() if e.checked_on else None}
                              for e in c.evidence_refs]}


@server.tool(name="propose_claim", description="[write] Propose a new claim or a change. Nothing is written until a second person approves the proposal in Constat. Returns the proposal id.")
def propose_claim(claim: dict, reason: str) -> dict:
    try:
        c = Claim.from_dict(claim)
        p = get_claim_store().propose(c, actor=ACTOR, reason=reason, today=date.today())
    except (ValueError, KeyError, TypeError) as e:
        _log("propose_claim", ok=False, error=str(e)[:200])
        return {"error": str(e)}
    _log("propose_claim", ok=True, proposal_id=p.proposal_id, claim_id=c.claim_id)
    return {"proposal_id": p.proposal_id, "status": p.status, "claim_id": c.claim_id,
            "note": "Pending approval by a claim owner; the author cannot approve their own proposal."}


@server.tool(name="record_sent_answer", description="[write] Record that a human sent an answer, pinning the claim versions it rested on. Only after a person approved and sent it outside this tool.")
def record_sent_answer(question: str, answer: str, claim_ids: list[str], approver: str, customer: str,
                       audience: str = "nda", difficulty_class: str = "covered") -> dict:
    store = get_claim_store()
    hashes = []
    for cid in claim_ids:
        c = store.get(cid)
        if c is None:
            return {"error": f"no claim {cid}"}
        hashes.append(c.version_hash())
    store.record_sent_answer(SentAnswerRecord(question=question, answer=answer, claim_ids=claim_ids,
                                              claim_version_hashes=hashes, approver=approver, customer=customer,
                                              sent_on=date.today(), audience=Audience(audience),
                                              difficulty_class=difficulty_class))
    _log("record_sent_answer", customer=customer, claims=claim_ids)
    return {"recorded": True, "claim_version_hashes": hashes}


def main() -> None:  # pragma: no cover
    if "--http" in sys.argv:
        port = int(sys.argv[sys.argv.index("--http") + 1]) if len(sys.argv) > sys.argv.index("--http") + 1 else 8020
        os.environ.setdefault("PORT", str(port))
        server.run(transport="streamable-http")
    else:
        server.run()


if __name__ == "__main__":  # pragma: no cover
    main()
