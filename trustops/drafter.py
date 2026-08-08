"""Drafters. The pipeline is drafter-agnostic by design: gates do not trust
the drafter, so swapping Mock -> Anthropic changes fluency, not safety posture.

MockDrafter      deterministic, retrieval-grounded, zero-dependency. Used for
                 CI, the eval suite, and offline demo runs.
AnthropicDrafter live LLM drafting under the Appendix B system contract, with
                 JSON-only structured output. Requires ANTHROPIC_API_KEY.
GeminiDrafter    same contract over the Gemini REST API via stdlib urllib —
                 no SDK install; free-tier friendly. Requires GEMINI_API_KEY.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .models import Citation, Coverage, Draft, Question, Risk
from .retrieve import Retriever

PROMPT_VERSION = "trustops-contract-v1.0"

SYSTEM_CONTRACT = """You are the TrustOps answer engine. Answer ONLY from the approved tenant \
source excerpts supplied in this request. Cite source_id and location for every factual claim. \
If evidence is missing, stale, contradictory, or outside scope, abstain and name the gap. \
Never infer certification, control operation, legal compliance, contract commitments, or roadmap \
outcomes. Return ONLY a JSON object: {"answer": string|null, "citations": [{"source_id": str, \
"location": str, "excerpt": str}], "abstained": bool, "gaps": [str], "risk": "low"|"medium"|"high"}. \
No prose outside the JSON."""


class MockDrafter:
    name = "mock"
    model_version = "deterministic-v1"

    def __init__(self, retriever: Retriever, threshold: float = 3.0):
        self.retriever = retriever
        self.threshold = threshold

    def draft(self, q: Question, tenant: str) -> Draft:
        hits = self.retriever.search(q.text, tenant=tenant, k=3)
        d = Draft(question_id=q.question_id, answer=None, drafter=self.name,
                  model_version=self.model_version, prompt_version=PROMPT_VERSION)
        strong = [h for h in hits if h.score >= self.threshold]
        if not strong:
            d.abstained = True
            d.gaps.append("Retrieval found no sufficiently relevant approved evidence.")
            return d
        top = strong[0]
        src = self.retriever.store.sources[top.chunk.source_id]
        excerpt = top.chunk.text.replace("\n", " ")
        excerpt = excerpt[:280] + ("…" if len(excerpt) > 280 else "")
        d.answer = f"Per {src.title} v{src.version}: {excerpt}"
        d.citations = [Citation(source_id=src.source_id, version=src.version,
                                location=top.chunk.location, excerpt=excerpt)]
        # a second strong hit from a different source becomes a supporting citation
        for h in strong[1:]:
            if h.chunk.source_id != top.chunk.source_id:
                s2 = self.retriever.store.sources[h.chunk.source_id]
                ex2 = h.chunk.text.replace("\n", " ")[:200]
                d.citations.append(Citation(source_id=s2.source_id, version=s2.version,
                                            location=h.chunk.location, excerpt=ex2))
                break
        d.risk = Risk.MEDIUM
        d.evidence_coverage = Coverage.PARTIAL  # provisional; post_gate finalizes
        return d


class AnthropicDrafter:
    """Live drafting. Same retrieval, same gates; the model only phrases within them."""

    name = "anthropic"

    def __init__(self, retriever: Retriever, model: str | None = None):
        import anthropic  # lazy: not required for offline/CI use

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model_version = model or os.environ.get("TRUSTOPS_MODEL", "claude-haiku-4-5-20251001")
        self.retriever = retriever

    def draft(self, q: Question, tenant: str) -> Draft:
        hits = self.retriever.search(q.text, tenant=tenant, k=4)
        d = Draft(question_id=q.question_id, answer=None, drafter=self.name,
                  model_version=self.model_version, prompt_version=PROMPT_VERSION)
        if not hits:
            d.abstained = True
            d.gaps.append("Retrieval found no relevant approved evidence.")
            return d
        evidence_block = "\n\n".join(
            f"[source_id={h.chunk.source_id} version="
            f"{self.retriever.store.sources[h.chunk.source_id].version} "
            f"location={h.chunk.location}]\n{h.chunk.text}"
            for h in hits
        )
        msg = self.client.messages.create(
            model=self.model_version,
            max_tokens=800,
            system=SYSTEM_CONTRACT,
            messages=[{"role": "user", "content":
                       f"QUESTION ({q.question_id}): {q.text}\n\nAPPROVED EXCERPTS:\n{evidence_block}"}],
        )
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            obj = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        except json.JSONDecodeError:
            d.abstained = True
            d.gaps.append("Drafter returned non-contract output; treated as abstention (fail-closed).")
            d.gate_flags.append("CONTRACT_PARSE_FAILURE")
            return d
        d.answer = obj.get("answer")
        d.abstained = bool(obj.get("abstained", d.answer is None))
        d.gaps.extend(obj.get("gaps", []))
        d.risk = Risk(obj.get("risk", "medium"))
        for c in obj.get("citations", []):
            sid = c.get("source_id", "")
            src = self.retriever.store.sources.get(sid)
            d.citations.append(Citation(
                source_id=sid,
                version=src.version if src else "?",
                location=c.get("location", "?"),
                excerpt=c.get("excerpt", "")[:280],
            ))
        return d


class GeminiDrafter:
    """Live drafting on Google's free tier. Same retrieval, same contract, same
    gates; plain REST via stdlib so live mode needs no extra install."""

    name = "gemini"

    def __init__(self, retriever: Retriever, model: str | None = None):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set (free key: aistudio.google.com)")
        # rolling alias: survives Google retiring dated models for new accounts
        self.model_version = model or os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
        self.retriever = retriever

    def _generate(self, user_msg: str) -> str:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model_version}:generateContent")
        body = json.dumps({
            "system_instruction": {"parts": [{"text": SYSTEM_CONTRACT}]},
            "contents": [{"parts": [{"text": user_msg}]}],
            # low thinking: the gates do the verification, not the model
            "generationConfig": {"responseMimeType": "application/json",
                                 "maxOutputTokens": 2048,
                                 "thinkingConfig": {"thinkingLevel": "low"}},
        }).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json", "x-goog-api-key": self.api_key})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    payload = json.loads(resp.read().decode())
                break
            except urllib.error.HTTPError as e:
                # free-tier RPM limits surface as 429; back off and retry
                if e.code in (429, 500, 503) and attempt < 4:
                    time.sleep(min(60, 15 * (attempt + 1)))
                    continue
                raise
        parts = payload["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)

    def draft(self, q: Question, tenant: str) -> Draft:
        hits = self.retriever.search(q.text, tenant=tenant, k=4)
        d = Draft(question_id=q.question_id, answer=None, drafter=self.name,
                  model_version=self.model_version, prompt_version=PROMPT_VERSION)
        if not hits:
            d.abstained = True
            d.gaps.append("Retrieval found no relevant approved evidence.")
            return d
        evidence_block = "\n\n".join(
            f"[source_id={h.chunk.source_id} version="
            f"{self.retriever.store.sources[h.chunk.source_id].version} "
            f"location={h.chunk.location}]\n{h.chunk.text}"
            for h in hits
        )
        raw = self._generate(
            f"QUESTION ({q.question_id}): {q.text}\n\nAPPROVED EXCERPTS:\n{evidence_block}")
        try:
            obj = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        except (json.JSONDecodeError, KeyError, IndexError):
            d.abstained = True
            d.gaps.append("Drafter returned non-contract output; treated as abstention (fail-closed).")
            d.gate_flags.append("CONTRACT_PARSE_FAILURE")
            return d
        d.answer = obj.get("answer")
        d.abstained = bool(obj.get("abstained", d.answer is None))
        d.gaps.extend(obj.get("gaps", []))
        d.risk = Risk(obj.get("risk", "medium"))
        for c in obj.get("citations", []):
            sid = c.get("source_id", "")
            src = self.retriever.store.sources.get(sid)
            d.citations.append(Citation(
                source_id=sid,
                version=src.version if src else "?",
                location=c.get("location", "?"),
                excerpt=c.get("excerpt", "")[:280],
            ))
        return d


def make_drafter(kind: str, retriever: Retriever):
    if kind == "mock":
        return MockDrafter(retriever)
    if kind == "anthropic":
        return AnthropicDrafter(retriever)
    if kind == "gemini":
        return GeminiDrafter(retriever)
    raise ValueError(f"unknown drafter '{kind}'")
