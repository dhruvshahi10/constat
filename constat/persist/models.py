"""Sidecar records. Plain dataclasses with to_row/from_row so SQLite and
Postgres share one shape; JSON columns hold lists and dicts."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class State(str, Enum):
    RECEIVED = "RECEIVED"
    NORMALISED = "NORMALISED"
    MATCHED = "MATCHED"
    DRAFTED = "DRAFTED"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    SENT = "SENT"
    HELD = "HELD"
    REFUSED = "REFUSED"
    QUARANTINED = "QUARANTINED"


_JSON_FIELDS = {"verdict_json", "payload_json", "artefact_json", "layout_json", "flags"}


class _Row:
    """Mixin: dataclass <-> flat dict row with JSON-encoded compound fields."""

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, Enum):
                d[k] = v.value
            elif k in _JSON_FIELDS or isinstance(v, (list, dict)):
                d[k] = json.dumps(v, ensure_ascii=False)
            elif isinstance(v, bool):
                d[k] = 1 if v else 0
        return d

    @classmethod
    def from_row(cls, row: dict[str, Any]):
        kw = {}
        for f in fields(cls):
            if f.name not in row:
                continue
            v = row[f.name]
            if f.name in _JSON_FIELDS and isinstance(v, str):
                v = json.loads(v) if v else ({} if f.name.endswith("_json") else [])
            elif f.type in ("bool", bool) or (isinstance(f.default, bool)):
                v = bool(v)
            elif f.type == "State" or f.type is State:
                v = State(v)
            kw[f.name] = v
        return cls(**kw)


@dataclass
class Questionnaire(_Row):
    id: str
    tenant: str
    customer: str
    filename: str
    sha256: str
    source_kind: str = "xlsx"            # xlsx | docx | csv | portal
    audience: str = "nda"
    deal_id: Optional[str] = None
    status: str = "received"             # received | normalising | processing | done | error
    layout_json: dict = field(default_factory=dict)   # detected spreadsheet layout, for export
    received_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class QuestionItem(_Row):
    id: str
    questionnaire_id: str
    tenant: str
    ordinal: int
    raw_text: str
    text: str = ""
    domain: str = ""
    row: Optional[int] = None            # original spreadsheet row, if any
    state: State = State.RECEIVED
    difficulty: str = ""
    verdict_json: dict = field(default_factory=dict)
    draft_answer: Optional[str] = None
    final_answer: Optional[str] = None
    claim_id: Optional[str] = None
    claim_version_hash: Optional[str] = None
    route: Optional[str] = None
    flags: list = field(default_factory=list)
    blocks_deal: bool = False
    duplicate_of: Optional[str] = None
    normaliser_model: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class ReviewAction(_Row):
    id: str
    item_id: str
    tenant: str
    actor: str
    action: str                          # approve | edit | route | reject | bulk_approve | send | transition
    note: str = ""
    before_answer: Optional[str] = None
    after_answer: Optional[str] = None
    at: str = field(default_factory=now_iso)


@dataclass
class Deal(_Row):
    id: str
    tenant: str
    customer: str
    value_usd: int = 0
    close_date: Optional[str] = None
    ae_email: str = ""
    approved_customer: bool = False      # gates automation level L2
    created_at: str = field(default_factory=now_iso)


@dataclass
class DegradationState(_Row):
    tenant: str
    primary_reviewer: str = ""
    backup_reviewer: str = ""
    last_review_at: Optional[str] = None
    mode: str = "normal"                 # normal | degraded
    entered_at: Optional[str] = None
    last_status_sent_at: Optional[str] = None
    ladder_level: int = 1                # 1 draft+review, 2 auto-send reused, 3 auto-send covered


@dataclass
class MetricEvent(_Row):
    id: str
    tenant: str
    kind: str                            # item_state | human_edit | follow_up | shipped_wrong | auto_sent | latency_ms | cost_usd | mcp_call
    item_id: Optional[str] = None
    deal_id: Optional[str] = None
    difficulty: str = ""
    value_num: float = 0.0
    payload_json: dict = field(default_factory=dict)
    at: str = field(default_factory=now_iso)


@dataclass
class ModelEvalRecord(_Row):
    id: str
    model_id: str
    prompt_version: str
    golden_pass_rate: float
    dangerous_failures: int
    injection_pass_rate: float
    cost_per_questionnaire_usd: float
    p95_latency_ms: int
    run_at: str = field(default_factory=now_iso)
    artefact_json: dict = field(default_factory=dict)


@dataclass
class Principal(_Row):
    id: str
    tenant: str
    email: str
    role: str                            # reviewer | owner | admin
    token_hash: str = ""
    source: str = "bearer"               # bearer | atlan_jwt
    created_at: str = field(default_factory=now_iso)


TABLES: dict[str, type] = {
    "questionnaires": Questionnaire,
    "question_items": QuestionItem,
    "review_actions": ReviewAction,
    "deals": Deal,
    "degradation_state": DegradationState,
    "metric_events": MetricEvent,
    "model_eval_records": ModelEvalRecord,
    "principals": Principal,
}
PRIMARY_KEY = {t: ("tenant" if t == "degradation_state" else "id") for t in TABLES}
