"""Constat as an Atlan App Framework app.

The App Framework (Python `application_sdk`) runs apps inside Atlan's
runtime: an App with typed Input and Output and a run() that plans, and
@task units that do the work with durable checkpoints. This wrapper is
deliberately thin: every task calls the same engine the API and CLI use.

Inputs: a questionnaire file reference, the customer, an optional deal id and
the audience. Output: counts by resting state and the questionnaire id, which
the embedded review queue then shows.

Without the SDK installed (local development, CI) the module still imports
and `run_locally()` executes the same plan in-process, so the wrapper is
tested without a tenant. The SDK's exact decorator and model names are taken
from docs.atlan.com (App, @task, Input, Output, FileReference); adjust the
import block if the installed SDK version differs. Docs:
https://docs.atlan.com/product/capabilities/build-apps/concepts/app-framework
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from constat.claims import Audience  # noqa: E402
from constat.claims.store import FileClaimStore  # noqa: E402
from constat.intake import parsers  # noqa: E402
from constat.integrations.slack import questionnaire_summary, post  # noqa: E402
from constat.persist import Questionnaire, make_repo, ulid  # noqa: E402
from constat.workflow.pipeline2 import PipelineConfig, create_items, process_questionnaire  # noqa: E402

try:  # pragma: no cover - depends on the SDK being installed inside Atlan's runtime
    from application_sdk import App, Input, Output, task  # type: ignore
    HAVE_SDK = True
except Exception:  # noqa: BLE001
    HAVE_SDK = False

    def task(**_kw):  # type: ignore
        def wrap(fn):
            return fn
        return wrap

    class Input:  # type: ignore
        pass

    class Output:  # type: ignore
        pass

    class App:  # type: ignore
        pass


@dataclass
class ConstatInput(Input):
    questionnaire_path: str
    customer: str
    tenant: str = "constat"
    deal_id: str | None = None
    audience: str = "nda"


@dataclass
class ConstatOutput(Output):
    questionnaire_id: str
    counts: dict
    notified: bool


def _store():
    kind = os.environ.get("CLAIM_STORE", "file")
    root = Path(os.environ.get("CLAIM_STORE_PATH", "data/claims"))
    if kind == "atlan":
        from constat.claims.atlan import AtlanClaimStore
        return AtlanClaimStore(os.environ.get("ATLAN_GLOSSARY", "Security Claims"), root / "sidecar")
    return FileClaimStore(root)


def _repo():
    return make_repo(os.environ.get("DATABASE_URL", "sqlite:///data/sidecar.db"))


@task(timeout_seconds=120)
def ingest(inp: ConstatInput) -> str:
    repo = _repo()
    data = Path(inp.questionnaire_path).read_bytes()
    tmp = Path(os.environ.get("CONSTAT_TMP", "/tmp/constat-app")) / ulid()
    tmp.mkdir(parents=True, exist_ok=True)
    parsed = parsers.parse(Path(inp.questionnaire_path).name, data, tmp)
    import hashlib
    q = Questionnaire(id=ulid(), tenant=inp.tenant, customer=inp.customer, filename=Path(inp.questionnaire_path).name,
                      sha256=hashlib.sha256(data).hexdigest(), source_kind=parsed.source_kind,
                      audience=inp.audience, deal_id=inp.deal_id)
    repo.insert("questionnaires", q)
    create_items(repo, q.id, inp.tenant, parsed.questions)
    return q.id


@task(timeout_seconds=1800)
def match_and_draft(questionnaire_id: str, audience: str) -> dict:
    repo, store = _repo(), _store()
    cfg = PipelineConfig(today=date.today(), audience=Audience(audience))
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        from constat.claims.drafter import HaikuClaimDrafter
        from constat.intake.normalise import HaikuNormaliser
        cfg.normaliser, cfg.drafter = HaikuNormaliser(key), HaikuClaimDrafter(key)
    return process_questionnaire(repo, questionnaire_id, store, cfg)


@task(timeout_seconds=30)
def notify(questionnaire_id: str, customer: str, counts: dict) -> bool:
    url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        return False
    return post(url, questionnaire_summary(customer, questionnaire_id, counts,
                                           link=os.environ.get("CONSTAT_WEB_URL", "")))


class ConstatApp(App):
    """Plan only: which tasks, in which order. No side effects here."""
    name = "constat"

    def run(self, inp: ConstatInput) -> ConstatOutput:
        qid = ingest(inp)
        counts = match_and_draft(qid, inp.audience)
        notified = notify(qid, inp.customer, counts)
        return ConstatOutput(questionnaire_id=qid, counts=counts, notified=notified)


def run_locally(inp: ConstatInput) -> ConstatOutput:
    return ConstatApp().run(inp)


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("questionnaire")
    ap.add_argument("--customer", required=True)
    ap.add_argument("--tenant", default="constat")
    ap.add_argument("--audience", default="nda")
    a = ap.parse_args()
    out = run_locally(ConstatInput(questionnaire_path=a.questionnaire, customer=a.customer, tenant=a.tenant, audience=a.audience))
    print(json.dumps(out.__dict__, indent=2))
