"""Seed a demo tenant: Acme claims, two deals, two questionnaires run through
the pipeline, a few approvals and sends, and a primary reviewer who has been
silent for four days so the degradation banner has something to say.

    CONSTAT_ENV=dev DATABASE_URL=sqlite:///data/sidecar.db CLAIM_STORE_PATH=data/claims \
    python scripts/seed_demo.py --tenant acme
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.auth import create_principal  # noqa: E402
from api.deps import get_claim_store, get_repo, get_settings  # noqa: E402
from constat.claims import Audience, Claim  # noqa: E402
from constat.intake.parsers import parse_xlsx  # noqa: E402
from constat.persist import Deal, Questionnaire, State, ulid  # noqa: E402
from constat.workflow import degradation as dg  # noqa: E402
from constat.workflow import review as rv  # noqa: E402
from constat.workflow.pipeline2 import PipelineConfig, create_items, process_questionnaire  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="acme")
    args = ap.parse_args()
    settings = get_settings()
    repo, store = get_repo(), get_claim_store()
    today = date.today()
    tenant = args.tenant

    if not store.list():
        spec = json.loads((ROOT / "evals/golden/claims_acme.json").read_text())
        store.bootstrap([Claim.from_dict(c) for c in spec["claims"]], approver="seed", today=today)
        print(f"claims: {len(store.list())}")

    reviewer, tok_r = create_principal(repo, tenant, "priya.nair@acme.example", "owner")
    backup, tok_b = create_principal(repo, tenant, "tom.osei@acme.example", "reviewer")
    print(f"reviewer token: {tok_r}\nbackup token:   {tok_b}")

    big = Deal(id=ulid(), tenant=tenant, customer="Northwind Bank", value_usd=420_000, ae_email="ae@acme.example",
               approved_customer=True, close_date=(today + timedelta(days=20)).isoformat())
    small = Deal(id=ulid(), tenant=tenant, customer="GitLab", value_usd=60_000, ae_email="ae2@acme.example")
    repo.insert("deals", big); repo.insert("deals", small)

    runs = []
    for fname, deal, customer in (("acme_security_questionnaire.xlsx", big, "Northwind Bank"),
                                  ("gitlab_caiq_v4_subset.xlsx", small, "GitLab")):
        q = Questionnaire(id=ulid(), tenant=tenant, customer=customer, filename=fname, sha256="demo",
                          deal_id=deal.id, audience="nda",
                          received_at=(datetime.now(timezone.utc) - timedelta(days=6)).isoformat(timespec="seconds"))
        repo.insert("questionnaires", q)
        parsed = parse_xlsx(ROOT / "data/questionnaires" / fname)
        items = create_items(repo, q.id, tenant, parsed.questions)
        for it in items[:3]:
            repo.update("question_items", it.id, {"blocks_deal": True})
        counts = process_questionnaire(repo, q.id, store, PipelineConfig(today=today, audience=Audience.NDA))
        runs.append((q, counts))
        print(f"{customer}: {counts}")

    ctx = rv.ReviewContext(repo=repo, store=store, actor=reviewer.email, today=today)
    q0 = runs[0][0]
    review = repo.list("question_items", {"questionnaire_id": q0.id, "state": State.REVIEW}, order="ordinal asc", limit=50)
    for it in review[:4]:
        rv.approve(ctx, it, "demo approval")
    for it in review[:2]:
        rv.send(ctx, it, q0.customer)
    held = repo.list("question_items", {"questionnaire_id": q0.id, "state": State.HELD}, limit=50)
    if held:
        rv.route(ctx, held[0], f"OWNER:{backup.email}", deadline=(today + timedelta(days=3)).isoformat(), note="please confirm")
    # make the primary reviewer look four days silent
    for a in repo.list("review_actions", {"tenant": tenant, "actor": reviewer.email}, limit=1000):
        repo.update("review_actions", a.id, {"at": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat(timespec="seconds")})
    dg.set_reviewers(repo, tenant, primary=reviewer.email, backup=backup.email, ladder_level=2)
    rep = dg.evaluate(repo, tenant)
    print(f"degradation: {rep.mode}, idle {rep.idle_hours}h, held {rep.held_count}, escalations {len(rep.escalations)}")
    print(f"settings: db={settings.database_url} claims={settings.claim_store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
