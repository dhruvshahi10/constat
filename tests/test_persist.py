from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constat.persist import (DegradationState, MetricEvent, QuestionItem, Questionnaire, State,
                             make_repo, ulid)


@pytest.fixture()
def repo(tmp_path):
    r = make_repo(f"sqlite:///{tmp_path / 'side.db'}")
    yield r
    r.close()


def test_ulid_sorts_by_time():
    a, b = ulid(1_000), ulid(2_000)
    assert len(a) == 26 and a < b


def test_round_trip_json_bool_and_enum(repo):
    q = Questionnaire(id=ulid(), tenant="acme", customer="N", filename="f.xlsx", sha256="s")
    repo.insert("questionnaires", q)
    it = QuestionItem(id=ulid(), questionnaire_id=q.id, tenant="acme", ordinal=1, raw_text="r",
                      flags=["A"], blocks_deal=True, verdict_json={"k": [1, 2]})
    repo.insert("question_items", it)
    got = repo.get("question_items", it.id)
    assert got.state is State.RECEIVED and got.flags == ["A"] and got.blocks_deal is True
    assert got.verdict_json == {"k": [1, 2]}


def test_update_list_count_and_in_clause(repo):
    q = Questionnaire(id=ulid(), tenant="acme", customer="N", filename="f.xlsx", sha256="s")
    repo.insert("questionnaires", q)
    ids = []
    for i, st in enumerate([State.REVIEW, State.SENT, State.HELD]):
        it = QuestionItem(id=ulid(), questionnaire_id=q.id, tenant="acme", ordinal=i, raw_text="r", state=st)
        repo.insert("question_items", it)
        ids.append(it.id)
    repo.update("question_items", ids[2], {"state": State.REVIEW, "flags": ["X"]})
    assert repo.count("question_items", {"tenant": "acme", "state": State.REVIEW}) == 2
    rows = repo.list("question_items", {"state": [State.REVIEW, State.SENT]}, order="ordinal desc")
    assert [r.ordinal for r in rows] == [2, 1, 0]
    with pytest.raises(KeyError):
        repo.update("question_items", "missing", {"state": State.SENT})
    with pytest.raises(ValueError):
        repo.list("question_items", order="ordinal; drop table x")


def test_upsert_on_tenant_keyed_table(repo):
    repo.upsert("degradation_state", DegradationState(tenant="acme", primary_reviewer="a@x"))
    repo.upsert("degradation_state", DegradationState(tenant="acme", primary_reviewer="b@x", mode="degraded"))
    d = repo.get("degradation_state", "acme")
    assert d.primary_reviewer == "b@x" and d.mode == "degraded"


def test_unknown_table_and_wrong_type(repo):
    with pytest.raises(KeyError):
        repo.get("nope", "x")
    with pytest.raises(TypeError):
        repo.insert("questionnaires", MetricEvent(id=ulid(), tenant="a", kind="x"))
