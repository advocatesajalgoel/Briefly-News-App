"""Similarity primitives for story clustering.

Pure Python, no heavy dependency: at the volumes Briefly ingests (a few
thousand articles a day) an inverted-index TF-IDF pass is fast enough and keeps
the deployment small. The :class:`EmbeddingProvider` seam means a vector model
can be dropped in later without touching the clusterer.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from app.text.normalize import entity_key, shingles, tokenize

Vector = dict[str, float]


def term_frequencies(tokens: list[str]) -> Counter[str]:
    return Counter(tokens)


def build_idf(documents: list[list[str]]) -> dict[str, float]:
    n = max(len(documents), 1)
    df: Counter[str] = Counter()
    for doc in documents:
        df.update(set(doc))
    return {term: math.log((n + 1) / (count + 1)) + 1.0 for term, count in df.items()}


def tfidf_vector(tokens: list[str], idf: dict[str, float]) -> Vector:
    tf = term_frequencies(tokens)
    if not tf:
        return {}
    max_tf = max(tf.values())
    vec: Vector = {}
    for term, count in tf.items():
        weight = (0.5 + 0.5 * count / max_tf) * idf.get(term, 1.0)
        if weight:
            vec[term] = weight
    return normalise(vec)


def normalise(vec: Vector) -> Vector:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm == 0:
        return {}
    return {k: v / norm for k, v in vec.items()}


def cosine(a: Vector, b: Vector) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return max(0.0, min(1.0, sum(w * b.get(t, 0.0) for t, w in a.items())))


def lexical_similarity(a: Vector, b: Vector) -> float:
    """Lexical closeness of two documents.

    Plain cosine over L2-normalised TF-IDF. An asymmetric containment measure
    was tried here first, on the theory that a short wire snap should still
    match a long write-up; on normalised vectors it reduces to cosine
    algebraically, and on raw weights it saturates at 1.0 for any short document
    whose words all appear somewhere in a long one — which merges unrelated
    stories. Length asymmetry is handled instead by
    :func:`app.pipeline.clustering.merge_on_shared_evidence`, which asks the
    sharper question: do these two documents name the same distinctive things?
    """
    return cosine(a, b)


def centroid(vectors: list[Vector]) -> Vector:
    if not vectors:
        return {}
    acc: Vector = {}
    for vec in vectors:
        for term, weight in vec.items():
            acc[term] = acc.get(term, 0.0) + weight
    return normalise({k: v / len(vectors) for k, v in acc.items()})


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


_ENTITY_NOISE = {"the", "of", "and", "for", "a", "an", "de", "mr", "ms", "dr",
                 "shri", "smt", "president", "minister", "governor", "chief",
                 "prime", "sir", "lt", "gen"}


@lru_cache(maxsize=65536)
def _entity_tokens(entity: str) -> frozenset[str]:
    return frozenset(t for t in entity_key(entity).split() if t and t not in _ENTITY_NOISE)


def _initialism(tokens: frozenset[str], ordered: list[str]) -> str:
    return "".join(t[0] for t in ordered if t)


def entities_match(a: str, b: str) -> bool:
    """Do two surface forms plausibly name the same thing?

    Handles the three cases that matter for news copy:
      * exact match after normalisation
      * one form contained in the other ("Reserve Bank" / "Reserve Bank of India")
      * an initialism of the other ("RBI" / "Reserve Bank of India")
    """
    ka, kb = entity_key(a), entity_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True

    ta, tb = _entity_tokens(a), _entity_tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True

    oa = [t for t in ka.split() if t not in _ENTITY_NOISE]
    ob = [t for t in kb.split() if t not in _ENTITY_NOISE]
    if len(ta) == 1 and len(tb) > 1:
        single = next(iter(ta))
        if len(single) >= 2 and single == _initialism(tb, ob):
            return True
    if len(tb) == 1 and len(ta) > 1:
        single = next(iter(tb))
        if len(single) >= 2 and single == _initialism(ta, oa):
            return True
    return False


def entity_overlap(entities_a: list[str], entities_b: list[str]) -> float:
    """Containment rather than plain Jaccard: a two-line wire snap naming two
    entities should still match a longer piece naming eight."""
    a = [e for e in entities_a if entity_key(e)]
    b = [e for e in entities_b if entity_key(e)]
    if not a or not b:
        return 0.0
    matched = 0
    unmatched_b = list(b)
    for ea in a:
        for i, eb in enumerate(unmatched_b):
            if entities_match(ea, eb):
                matched += 1
                unmatched_b.pop(i)
                break
    return matched / min(len(a), len(b))


def shingle_overlap(text_a: str, text_b: str, n: int = 3) -> float:
    """Fraction of ``text_a``'s n-grams that also appear in ``text_b``.

    Used by quality control to catch prose that leans too close to a source's
    wording. Asymmetric on purpose: we care how much of *our* text is borrowed.
    """
    a = shingles(tokenize(text_a, drop_stopwords=False), n)
    b = shingles(tokenize(text_b, drop_stopwords=False), n)
    if not a:
        return 0.0
    return len(a & b) / len(a)


@dataclass(frozen=True)
class SimilarityWeights:
    lexical: float = 0.55
    entity: float = 0.30
    numeric: float = 0.15

    def total(self) -> float:
        return self.lexical + self.entity + self.numeric


DEFAULT_WEIGHTS = SimilarityWeights()


def composite_similarity(
    lexical: float,
    entity: float,
    numeric: float,
    weights: SimilarityWeights = DEFAULT_WEIGHTS,
) -> float:
    total = weights.total() or 1.0
    score = (
        weights.lexical * lexical + weights.entity * entity + weights.numeric * numeric
    ) / total
    return max(0.0, min(1.0, score))


class EmbeddingProvider:
    """Interface for a vector backend. ``none`` is the default and does nothing."""

    name = "none"

    def available(self) -> bool:
        return False

    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover - interface
        raise NotImplementedError


def cosine_dense(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))
