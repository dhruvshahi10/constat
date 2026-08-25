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
import re
import time
import urllib.error
import urllib.request

from .models import Citation, Coverage, Draft, Question, Risk
from .retrieve import Retriever

PROMPT_VERSION = "constat-contract-v1.0"

# Hard cap on how much of any one chunk is handed to a model, and on how much of
# it we store back as a citation excerpt. Chunking is paragraph-sized, but a
# pathological source (a wall-of-text page, a table flattened into one block)
# could otherwise put an entire document into a single prompt or into the
# customer-facing provenance strip. 1200 characters is roughly two dense
# paragraphs: enough to answer a questionnaire item, far short of a document.
MAX_EXCERPT_CHARS = 1200

_SENTENCE_END = re.compile(r"[.!?](?=\s|$)|\n")

SYSTEM_CONTRACT = """You are the Constat answer engine. Answer ONLY from the approved tenant \
source excerpts supplied in this request. Cite source_id and location for every factual claim. \
If evidence is missing, stale, contradictory, or outside scope, abstain and name the gap. \
Never infer certification, control operation, legal compliance, contract commitments, or roadmap \
outcomes. Return ONLY a JSON object: {"answer": string|null, "citations": [{"source_id": str, \
"location": str, "excerpt": str}], "abstained": bool, "gaps": [str], "risk": "low"|"medium"|"high"}. \
No prose outside the JSON."""


# --- excerpt custody ---------------------------------------------------------
def clip_excerpt(text: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    """Cap text at `limit`, trimming at a sentence boundary where one is close
    to the cap, otherwise at a word boundary. Never cuts mid-word."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    window = text[:limit]
    best = -1
    for m in _SENTENCE_END.finditer(window):
        best = m.end()
    if best >= int(limit * 0.6):
        return window[:best].rstrip() + " …"
    space = window.rfind(" ")
    cut = space if space > 0 else limit
    return window[:cut].rstrip(" ,;:") + " …"


def _flatten(text: str) -> str:
    return " ".join((text or "").split())


def chunk_index(retriever: Retriever) -> dict[tuple[str, str], str]:
    """(source_id, location) -> real chunk text, for the whole tenant store.

    This is the ground truth a model citation is resolved against. A location
    the store has never emitted does not exist, however plausible it reads.
    """
    return {(c.source_id, c.location): c.text for c in retriever.store.chunks()}


def evidence_block(retriever: Retriever, hits) -> str:
    """The excerpts actually transmitted to the model, each capped."""
    return "\n\n".join(
        f"[source_id={h.chunk.source_id} version="
        f"{retriever.store.sources[h.chunk.source_id].version} "
        f"location={h.chunk.location}]\n{clip_excerpt(h.chunk.text)}"
        for h in hits
    )


def resolve_citations(raw_citations, hits, retriever: Retriever,
                      index: dict[tuple[str, str], str]):
    """Resolve model-authored citations against reality.

    Two separate trust problems are fixed here:

      1. The model can attach a real source_id to a claim it invented, or name a
         location that does not exist. Every (source_id, location) pair must
         resolve to a chunk that was actually retrieved for THIS question;
         anything else is dropped and the drop is recorded as a gap.
      2. The model can author the excerpt itself, which would put model prose
         into the provenance strip we sell as the customer's own document text.
         The model's excerpt is discarded unconditionally and replaced with the
         real chunk text from the store.

    Returns (citations, gaps, flags).
    """
    retrieved = {(h.chunk.source_id, h.chunk.location) for h in hits}
    retrieved_sources = {sid for sid, _ in retrieved}
    out: list[Citation] = []
    gaps: list[str] = []
    flags: list[str] = []
    seen: set[tuple[str, str]] = set()

    for c in raw_citations or []:
        if not isinstance(c, dict):
            continue
        sid = str(c.get("source_id") or "").strip()
        loc = str(c.get("location") or "").strip()
        if sid not in retrieved_sources:
            gaps.append(
                f"Citation to '{sid or '(unnamed source)'}' dropped: that source was not "
                "among the excerpts retrieved for this question, so it cannot support it."
            )
            flags.append("FABRICATED_CITATION")
            continue
        if (sid, loc) not in index:
            gaps.append(
                f"Citation {sid}@{loc or '(no location)'} dropped: that location does not "
                "exist in the source document."
            )
            flags.append("HALLUCINATED_LOCATION")
            continue
        if (sid, loc) not in retrieved:
            gaps.append(
                f"Citation {sid}@{loc} dropped: that passage exists but was not retrieved "
                "for this question, so the drafter never saw it."
            )
            flags.append("UNRETRIEVED_CITATION")
            continue
        if (sid, loc) in seen:
            continue
        seen.add((sid, loc))
        src = retriever.store.sources.get(sid)
        out.append(Citation(
            source_id=sid,
            version=src.version if src else "?",
            # the model's excerpt is never stored: provenance is the customer's
            # own text or it is nothing
            excerpt=clip_excerpt(_flatten(index[(sid, loc)])),
            location=loc,
        ))
    # de-duplicate flags, preserve first-seen order
    flags = list(dict.fromkeys(flags))
    return out, gaps, flags


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
        self.model_version = model or os.environ.get("CONSTAT_MODEL", "claude-haiku-4-5-20251001")
        self.retriever = retriever
        self._index = chunk_index(retriever)

    def draft(self, q: Question, tenant: str) -> Draft:
        hits = self.retriever.search(q.text, tenant=tenant, k=4)
        d = Draft(question_id=q.question_id, answer=None, drafter=self.name,
                  model_version=self.model_version, prompt_version=PROMPT_VERSION)
        if not hits:
            d.abstained = True
            d.gaps.append("Retrieval found no relevant approved evidence.")
            return d
        block = evidence_block(self.retriever, hits)
        # custody receipt: exactly how much customer text left the machine
        d.gate_flags.append(f"EVIDENCE_CHARS:{len(block)}")
        msg = self.client.messages.create(
            model=self.model_version,
            max_tokens=800,
            system=SYSTEM_CONTRACT,
            messages=[{"role": "user", "content":
                       f"QUESTION ({q.question_id}): {q.text}\n\nAPPROVED EXCERPTS:\n{block}"}],
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
        cites, gaps, flags = resolve_citations(
            obj.get("citations", []), hits, self.retriever, self._index)
        d.citations = cites
        d.gaps.extend(gaps)
        d.gate_flags.extend(flags)
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
        self._index = chunk_index(retriever)
        # free tier is ~10 req/min: self-pace instead of hammering into 429s
        self.min_interval = float(os.environ.get("GEMINI_MIN_INTERVAL", "6.5"))
        self._last_call = 0.0

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
        wait = self._last_call + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        for attempt in range(5):
            self._last_call = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    payload = json.loads(resp.read().decode())
                break
            except urllib.error.HTTPError as e:
                # free-tier RPM limits surface as 429; back off and retry
                if e.code in (429, 500, 503) and attempt < 4:
                    time.sleep(min(90, 20 * (attempt + 1)))
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
        block = evidence_block(self.retriever, hits)
        # custody receipt: exactly how much customer text left the machine
        d.gate_flags.append(f"EVIDENCE_CHARS:{len(block)}")
        try:
            raw = self._generate(
                f"QUESTION ({q.question_id}): {q.text}\n\nAPPROVED EXCERPTS:\n{block}")
        except OSError as exc:
            # transport failure (rate limit exhausted, network down): the run
            # must degrade to an abstention, never crash and never fabricate
            d.abstained = True
            d.gaps.append(f"Live drafter unavailable ({type(exc).__name__}), "
                          "fail-closed abstention; retry later or answer via SME.")
            d.gate_flags.append("DRAFTER_UNAVAILABLE")
            return d
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
        cites, gaps, flags = resolve_citations(
            obj.get("citations", []), hits, self.retriever, self._index)
        d.citations = cites
        d.gaps.extend(gaps)
        d.gate_flags.extend(flags)
        return d


def make_drafter(kind: str, retriever: Retriever):
    if kind == "mock":
        return MockDrafter(retriever)
    if kind == "anthropic":
        return AnthropicDrafter(retriever)
    if kind == "gemini":
        return GeminiDrafter(retriever)
    raise ValueError(f"unknown drafter '{kind}'")
