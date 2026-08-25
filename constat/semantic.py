"""Semantic retrieval: a drop-in Retriever with meaning-aware scoring.

Two embedder backends behind one interface:

  OnnxEmbedder        fastembed + BAAI/bge-small-en-v1.5, the production model.
                      Baked into the Docker image at build time so runtime has
                      zero network egress of customer text (or anything else).
  HashedNgramEmbedder character 3-5 gram hashing into a fixed dense space,
                      pure stdlib. Deterministic, instant, always available.
                      Bridges morphology (hosted/hosting, region/regions) and
                      is the guaranteed floor when the model is absent.

Scoring is hybrid and threshold-compatible with the lexical Retriever that
MockDrafter calibrates against (>= 3.0): the base lexical score is kept and a
cosine term is added only above a floor, so junk queries still fail closed.

Tenant isolation is enforced at BOTH ends: build_index stamps the tenant and
refuses foreign chunks; search re-checks the stamp, the caller's tenant, and
every hit. A tampered index meta raises before any chunk is returned.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path

from .evidence import EvidenceStore, validate_tenant
from .models import Chunk
from .retrieve import Hit, tokens

COSINE_FLOOR = 0.35
COSINE_WEIGHT = 4.0
NGRAM_DIM = 512

# Small, generic GRC vocabulary bridge. Deliberately domain-level (how security
# questionnaires talk) rather than tenant-level; the embedding model subsumes
# it, but it keeps the no-model floor genuinely useful.
SYNONYMS: dict[str, set[str]] = {
    "host": {"hosting", "aws", "amazon", "azure", "gcp", "cloud", "datacenter"},
    "provider": {"vendor", "subprocessor", "aws", "amazon", "azure", "gcp", "cloud"},
    "region": {"us-east", "eu-west", "datacenter", "zone"},
    "penetration": {"pentest"},
    "mfa": {"multi-factor", "two-factor", "2fa"},
    "delete": {"deletion", "erasure", "disposal", "purge"},
    "encrypt": {"tls", "aes", "cipher", "cryptographic"},
    "breach": {"incident"},
    "vendor": {"subprocessor", "third-party", "supplier"},
    "employee": {"workforce", "personnel", "staff"},
}


def _stem(token: str) -> str:
    """Crude but symmetric: hosted/hosting -> host, regions -> region."""
    t = re.sub(r"[\.\d]+$", "", token).rstrip("-")
    for suffix in ("ings", "ing", "ed", "es", "s"):
        if t.endswith(suffix) and len(t) - len(suffix) >= 3:
            return t[: -len(suffix)]
    return t


def _stemmed(tokens_set: set[str]) -> set[str]:
    return {_stem(t) for t in tokens_set}


def _expand(stems: set[str]) -> set[str]:
    out = set(stems)
    for s in stems:
        out |= {_stem(x) for x in SYNONYMS.get(s, ())}
    return out


# ── embedders ────────────────────────────────────────────────────────────────
class HashedNgramEmbedder:
    """Character n-gram hashing embedder. No deps, no model, no network."""

    name = "hashed-ngram-v1"
    dim = NGRAM_DIM

    def _grams(self, text: str):
        text = unicodedata.normalize("NFKD", text.lower())
        text = re.sub(r"[^a-z0-9 ]+", " ", text)
        for word in text.split():
            padded = f" {word} "
            for n in (3, 4, 5):
                for i in range(len(padded) - n + 1):
                    yield padded[i:i + n]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for gram in self._grams(text):
                h = int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=4).digest(),
                                   "big")
                vec[h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0  # signed hashing
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class OnnxEmbedder:
    """fastembed bge-small. Import and model load are deferred so environments
    without the model fall back cleanly."""

    name = "bge-small-en-v1.5"
    dim = 384

    def __init__(self) -> None:
        from fastembed import TextEmbedding
        self._model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


def best_embedder():
    """Production model if importable and cached; the hashed floor otherwise."""
    try:
        return OnnxEmbedder()
    except Exception:  # noqa: BLE001 — any failure means: use the floor
        return HashedNgramEmbedder()


# ── index ────────────────────────────────────────────────────────────────────
def build_index(store: EvidenceStore, index_dir: Path, embedder) -> None:
    chunks = store.chunks()
    for c in chunks:
        if c.tenant != store.tenant:
            raise PermissionError(
                f"foreign chunk in build: store is '{store.tenant}', chunk is '{c.tenant}'")
    vectors = embedder.embed([c.text for c in chunks]) if chunks else []
    corpus = hashlib.sha256(
        "".join(sorted(s.sha256 for s in store.sources.values())).encode()).hexdigest()
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "index.json").write_text(json.dumps({
        "tenant": store.tenant, "model": embedder.name, "dim": embedder.dim,
        "corpus_sha256": corpus,
        "chunks": [{"source_id": c.source_id, "tenant": c.tenant,
                    "location": c.location, "text": c.text} for c in chunks],
        "vectors": vectors,
    }, ensure_ascii=False), encoding="utf-8")


def corpus_sha(store: EvidenceStore) -> str:
    return hashlib.sha256(
        "".join(sorted(s.sha256 for s in store.sources.values())).encode()).hexdigest()


class SemanticRetriever:
    """Drop-in for constat.retrieve.Retriever. Same constructor arity is not
    required by callers (pipeline injects instances), but search() is."""

    def __init__(self, store: EvidenceStore, index_dir: Path, embedder) -> None:
        self.store = store
        self.embedder = embedder
        raw = json.loads((index_dir / "index.json").read_text(encoding="utf-8"))
        if raw["tenant"] != store.tenant:
            raise PermissionError(
                f"index tenant mismatch: index is '{raw['tenant']}', "
                f"store is '{store.tenant}'")
        if raw["model"] != embedder.name:
            raise ValueError(f"index built with '{raw['model']}', "
                             f"searcher uses '{embedder.name}'; rebuild")
        if raw["corpus_sha256"] != corpus_sha(store):
            raise ValueError("index is stale for this evidence set; rebuild")
        self._chunks = [Chunk(**c) for c in raw["chunks"]]
        for c in self._chunks:
            if c.tenant != store.tenant:
                raise PermissionError("foreign chunk in index; refusing to search")
        self._vectors = raw["vectors"]

    def search(self, query: str, tenant: str, k: int = 4) -> list[Hit]:
        # same reasoning as retrieve.Retriever.search: an unvalidated name can
        # satisfy the mismatch check by matching a store built from the same
        # crafted string. This is the retriever the hosted server uses.
        validate_tenant(tenant)
        if tenant != self.store.tenant:
            raise PermissionError(
                f"tenant mismatch: store is '{self.store.tenant}', query is '{tenant}'")
        qtok = tokens(query)
        qstem = _stemmed(qtok)
        qexp = _expand(qstem)
        qvec = self.embedder.embed([query])[0]
        scored: list[Hit] = []
        for chunk, vec in zip(self._chunks, self._vectors):
            cstem = _stemmed(tokens(chunk.text))
            lexical = len(qtok & tokens(chunk.text))
            # synonym/stem bridge: matches beyond raw overlap, capped so the
            # lexicon can nudge a ranking but never fabricate relevance
            bridged = min(len((qexp & cstem) - _stemmed(qtok & tokens(chunk.text))), 3)
            src = self.store.sources.get(chunk.source_id)
            topic_boost = sum(
                1.5 for t in (src.topics if src else [])
                if t in query.lower() or _stemmed(set(t.split())) <= qexp)
            cosine = sum(a * b for a, b in zip(qvec, vec))
            semantic = COSINE_WEIGHT * cosine if cosine >= COSINE_FLOOR else 0.0
            score = lexical + bridged + topic_boost + semantic
            if score > 0:
                scored.append(Hit(chunk=chunk, score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        top = scored[:k]
        for h in top:
            assert h.chunk.tenant == tenant, "cross-tenant leak"
        return top
