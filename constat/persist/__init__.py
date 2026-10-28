"""Sidecar persistence: everything that is not a claim.

Claims live in the claim store (file or Atlan glossary). Questionnaires,
question items and their state machine, review actions, deals, degradation
state, metric events, model-evaluation records and principals live here, in
SQLite locally and Postgres when hosted, behind one small Repository
interface so the engine never knows which.
"""
from .ids import ulid
from .models import (Deal, DegradationState, MetricEvent, ModelEvalRecord, Principal,
                     Questionnaire, QuestionItem, ReviewAction, State)
from .repo import Repository, make_repo

__all__ = ["Deal", "DegradationState", "MetricEvent", "ModelEvalRecord", "Principal",
           "Questionnaire", "QuestionItem", "ReviewAction", "Repository", "State",
           "make_repo", "ulid"]
