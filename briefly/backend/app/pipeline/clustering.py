"""Story clustering: many articles about one event become one story.

Strategy — cheap signals first, expensive ones only if needed:

1. Restrict candidates to a time window (an event reported 3 days apart is
   usually a follow-up, not the same story).
2. Score each pair on three axes: lexical TF-IDF cosine, named-entity
   containment, and shared numbers.
3. Single-link agglomeration over the composite score, with a guard that stops
   two clusters merging when their entity sets barely intersect (this is what
   keeps "Delhi metro fare hike" and "Mumbai metro fare hike" apart).

The :class:`EmbeddingProvider` seam lets a vector model contribute to the
lexical axis later without changing anything else.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.text.gazetteer import cities_in
from app.text.normalize import entity_key, extract_entities, extract_numbers, tokenize
from app.text.similarity import (
    DEFAULT_WEIGHTS,
    SimilarityWeights,
    Vector,
    build_idf,
    centroid,
    composite_similarity,
    cosine,
    cosine_dense,
    entity_overlap,
    jaccard,
    lexical_similarity,
    tfidf_vector,
)


@dataclass
class ClusterItem:
    """One article as the clusterer sees it."""

    key: str                      # stable id (the Article uuid, as text)
    headline: str
    summary: str = ""
    published_at: datetime | None = None
    source_slug: str = ""
    tokens: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    vector: Vector = field(default_factory=dict)
    embedding: list[float] | None = None
    distinctive: set[str] = field(default_factory=set)
    # Second-pass evidence: stemmed content terms with generic words removed,
    # the same for the headline alone, and each term's weight in this batch.
    evidence: set[str] = field(default_factory=set)
    head_evidence: set[str] = field(default_factory=set)
    evidence_weight: dict[str, float] = field(default_factory=dict)
    # Headline terms few enough reports use that sharing one means something.
    # On a day with eight unrelated stories about the central bank, its name in
    # two headlines is not evidence that they are the same story.
    head_specific: set[str] = field(default_factory=set)
    # City-level places named, resolved once: the guard that keeps lookalike
    # events in different cities apart is consulted for every candidate pair.
    cities: frozenset[str] = frozenset()

    @property
    def text(self) -> str:
        return f"{self.headline}. {self.summary}".strip()

    @property
    def entity_keys(self) -> set[str]:
        return {entity_key(e) for e in self.entities if entity_key(e)}


@dataclass
class Cluster:
    items: list[ClusterItem] = field(default_factory=list)
    centroid_vector: Vector = field(default_factory=dict)
    distinctive: set[str] = field(default_factory=set)

    @property
    def keys(self) -> list[str]:
        return [i.key for i in self.items]

    @property
    def entity_keys(self) -> set[str]:
        keys: set[str] = set()
        for item in self.items:
            keys |= item.entity_keys
        return keys

    @property
    def source_slugs(self) -> set[str]:
        return {i.source_slug for i in self.items if i.source_slug}

    @property
    def cities(self) -> set[str]:
        found: set[str] = set()
        for item in self.items:
            found |= item.cities
        return found

    @property
    def earliest(self) -> datetime | None:
        stamps = [i.published_at for i in self.items if i.published_at]
        return min(stamps) if stamps else None

    @property
    def latest(self) -> datetime | None:
        stamps = [i.published_at for i in self.items if i.published_at]
        return max(stamps) if stamps else None

    def representative(self) -> ClusterItem:
        """The item closest to the cluster centre — used to seed the headline."""
        if len(self.items) == 1:
            return self.items[0]
        best, best_score = self.items[0], -1.0
        for item in self.items:
            score = cosine(item.vector, self.centroid_vector)
            if score > best_score:
                best, best_score = item, score
        return best


# A token is "distinctive" when only a handful of documents in the batch use it.
# Kept as a cheap descriptive signal on each cluster; it no longer decides
# merges on its own — see ``same_event_evidence`` for why.
DISTINCTIVE_MAX_DOC_FRACTION = 0.02
DISTINCTIVE_MAX_DOCS = 4


def _distinctive_terms(documents: list[list[str]]) -> set[str]:
    df: Counter[str] = Counter()
    for doc in documents:
        df.update(set(doc))
    ceiling = max(DISTINCTIVE_MAX_DOCS, int(len(documents) * DISTINCTIVE_MAX_DOC_FRACTION))
    return {term for term, count in df.items() if count <= ceiling}


# Words that turn up in unrelated stories on the same day and therefore prove
# nothing when two reports share them. Days and months are here because "on
# Monday" is in half of Monday's news; offices and institutions are here
# because "the president", "police" and "the court" appear in a hundred
# different events. Sharing a *name* still counts — sharing a job title does
# not.
GENERIC_EVIDENCE = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "today", "yesterday",
    "tomorrow", "week", "month", "year", "day", "night", "morning", "evening",
    "president", "minister", "prime", "chief", "government", "govt", "police",
    "court", "official", "state", "country", "national", "people", "leader",
    "party", "spokesperson", "source", "statement", "announce", "announc",
    "claim", "tell", "told", "add", "accord", "make", "made", "take", "took",
    "get", "got", "set", "call", "hold", "held", "come", "came", "go", "went",
    "first", "second", "third", "last", "next", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine", "ten", "many", "several", "top",
    "big", "major", "key", "latest", "update", "live", "watch", "video",
    "amid", "after", "before", "over", "ahead", "near", "across", "against",
    "us", "uk", "mr", "ms", "dr", "sir", "time", "year-old", "old",
    # Units. "6.5 per cent" in two headlines is compared as a figure, with its
    # unit attached; the bare words "per" and "cent" are in every business
    # story of the day and say nothing on their own.
    "per", "cent", "percent", "crore", "lakh", "million", "billion", "trillion",
    "thousand", "rs", "rupee", "dollar", "usd", "inr", "km", "kg", "tonne",
}

# A headline term stops being evidence of "the same event" once this share of
# the batch uses it. Small batches get a floor so a handful of reports of one
# story are never mistaken for a crowd.
SPECIFIC_MAX_DOC_FRACTION = 0.04
SPECIFIC_MIN_DOCS = 8


def specific_ceiling(batch_size: int) -> int:
    return max(SPECIFIC_MIN_DOCS, math.ceil(batch_size * SPECIFIC_MAX_DOC_FRACTION))

_STEM_SUFFIXES = ("ingly", "edly", "ing", "ies", "ied", "ed", "es", "s")


def stem(token: str) -> str:
    """A very light stemmer: enough to match rate/rates and strike/strikes.

    Deliberately crude. It only has to make two reports of one event agree on
    their own vocabulary, and a real stemmer's mistakes ("university" and
    "universe") would manufacture agreement that is not there.
    """
    if len(token) <= 4 or token.isdigit():
        return token
    if token.endswith(("ies", "ied")) and len(token) > 5:
        return token[:-3] + "y"
    for suffix in _STEM_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            if suffix == "s" and token.endswith(("ss", "us", "is")):
                return token
            return token[: -len(suffix)]
    return token


def evidence_terms(text: str) -> set[str]:
    out: set[str] = set()
    for token in tokenize(text):
        if token.isdigit():
            # Figures are compared separately, with their units attached.
            continue
        stemmed = stem(token)
        if stemmed in GENERIC_EVIDENCE or token in GENERIC_EVIDENCE:
            continue
        out.add(stemmed)
    return out


def build_items(rows: list[dict]) -> list[ClusterItem]:
    """``rows`` are dicts with key/headline/summary/published_at/source_slug."""
    items = [
        ClusterItem(
            key=str(r["key"]),
            headline=r.get("headline") or "",
            summary=r.get("summary") or "",
            published_at=r.get("published_at"),
            source_slug=r.get("source_slug") or "",
            embedding=r.get("embedding"),
        )
        for r in rows
    ]
    for item in items:
        item.tokens = tokenize(item.text)
        item.entities = extract_entities(item.text)
        item.numbers = [n.lower().replace(" ", "") for n in extract_numbers(item.text)]

    idf = build_idf([i.tokens for i in items])
    rare = _distinctive_terms([i.tokens for i in items])
    for item in items:
        item.vector = tfidf_vector(item.tokens, idf)
        item.distinctive = set(item.tokens) & rare
        # Figures are distinctive by nature and survive rewording, so they count
        # even when they are common enough to fall under the IDF cutoff.
        item.distinctive |= {n for n in item.numbers if len(n) >= 3}
        item.evidence = evidence_terms(item.text)
        item.head_evidence = evidence_terms(item.headline)
        item.cities = frozenset(cities_in(item.entities))

    evidence_idf = build_idf([sorted(i.evidence) for i in items])
    evidence_df: Counter[str] = Counter()
    for item in items:
        evidence_df.update(item.evidence)
    ceiling = specific_ceiling(len(items))
    for item in items:
        item.evidence_weight = {t: evidence_idf.get(t, 1.0) for t in item.evidence}
        item.head_specific = {t for t in item.head_evidence if evidence_df[t] <= ceiling}
    return items


def pair_similarity(
    a: ClusterItem, b: ClusterItem, weights: SimilarityWeights = DEFAULT_WEIGHTS
) -> float:
    lexical = lexical_similarity(a.vector, b.vector)
    if a.embedding and b.embedding:
        lexical = max(lexical, cosine_dense(a.embedding, b.embedding))
    ent = entity_overlap(a.entities, b.entities)
    num = jaccard(set(a.numbers), set(b.numbers))
    return composite_similarity(lexical, ent, num, weights)


def _within_window(a: ClusterItem, b: ClusterItem, hours: int) -> bool:
    if not a.published_at or not b.published_at:
        return True
    return abs(a.published_at - b.published_at) <= timedelta(hours=hours)


def _first_pass_link(
    a: ClusterItem,
    b: ClusterItem,
    *,
    threshold: float,
    min_entity_overlap: float,
    weights: SimilarityWeights,
) -> bool:
    """Are two reports worded alike *and* about the same things?"""
    if pair_similarity(a, b, weights) < threshold:
        return False
    # Two reports set in different cities are not the same event, however
    # similar the wording. This guard is what keeps "Delhi Metro fares to
    # rise" apart from "Mumbai Metro fares to rise", which share almost every
    # word. Only city names are compared — see the gazetteer for why.
    if a.cities and b.cities and not (a.cities & b.cities):
        return False
    # Two pieces can share a lot of vocabulary and still be different events,
    # so require corroborating evidence that the same *things* are involved:
    # overlapping actors, or overlapping figures. Publishers often name the
    # actor differently ("the central bank" / "the committee"), so a shared
    # figure counts on its own.
    if a.entity_keys and b.entity_keys:
        ent = entity_overlap(a.entities, b.entities)
        num = jaccard(set(a.numbers), set(b.numbers))
        if ent < min_entity_overlap and num <= 0.0:
            return False
    return True


def candidate_ceiling(batch_size: int) -> int:
    """How many reports may share a word before it stops proposing pairs.

    A word in a twentieth of the day's reports ("india", "minister", "says")
    cannot tell two stories apart, and scoring every pair that shares it is
    what turns a 1,500-article batch from seconds into minutes. Two reports of
    one event always share something rarer than that.
    """
    return max(60, math.ceil(batch_size * 0.06))


def cluster_items(
    items: list[ClusterItem],
    *,
    threshold: float | None = None,
    window_hours: int | None = None,
    min_entity_overlap: float = 0.20,
    weights: SimilarityWeights = DEFAULT_WEIGHTS,
) -> list[Cluster]:
    """Single-link agglomeration, a second evidence pass, then a coherence check."""
    settings = get_settings()
    threshold = settings.cluster_similarity_threshold if threshold is None else threshold
    window_hours = settings.cluster_time_window_hours if window_hours is None else window_hours

    if not items:
        return []

    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    # Inverted index on tokens so we only score plausible pairs.
    postings: dict[str, list[int]] = defaultdict(list)
    for idx, item in enumerate(items):
        for term in set(item.tokens):
            postings[term].append(idx)

    ceiling = candidate_ceiling(len(items))
    candidates: set[tuple[int, int]] = set()
    for _term, idxs in postings.items():
        if len(idxs) < 2 or len(idxs) > ceiling:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                candidates.add((idxs[a], idxs[b]))

    for i, j in sorted(candidates):
        if find(i) == find(j):
            continue
        a, b = items[i], items[j]
        if not _within_window(a, b, window_hours):
            continue
        if _first_pass_link(a, b, threshold=threshold,
                            min_entity_overlap=min_entity_overlap, weights=weights):
            union(i, j)

    grouped: dict[int, list[ClusterItem]] = defaultdict(list)
    for idx, item in enumerate(items):
        grouped[find(idx)].append(item)

    clusters: list[Cluster] = [_make_cluster(members) for members in grouped.values()]
    clusters = merge_on_shared_evidence(clusters, window_hours=window_hours)

    def linked(a: ClusterItem, b: ClusterItem) -> bool:
        if not _within_window(a, b, window_hours):
            return False
        if a.cities and b.cities and not (a.cities & b.cities):
            return False
        if _first_pass_link(a, b, threshold=threshold,
                            min_entity_overlap=min_entity_overlap, weights=weights):
            return True
        return (
            lexical_similarity(a.vector, b.vector) >= EVIDENCE_LEXICAL_FLOOR
            and same_event_evidence(a, b).same_event
        )

    coherent: list[Cluster] = []
    for cluster in clusters:
        coherent.extend(split_incoherent(cluster, linked))
    coherent.sort(key=lambda c: (-len(c.items), c.earliest or datetime.max.replace(tzinfo=UTC)))
    return coherent


def _make_cluster(members: list[ClusterItem]) -> Cluster:
    members = sorted(members, key=lambda m: (m.published_at or datetime.max.replace(tzinfo=UTC)))
    shared: set[str] = set()
    for member in members:
        shared |= member.distinctive
    return Cluster(
        items=members,
        centroid_vector=centroid([m.vector for m in members]),
        distinctive=shared,
    )


def looks_welded(cluster: Cluster) -> bool:
    """Does this cluster have the shape of several stories stuck together?

    One event draws one or two reports from each outlet covering it. A cluster
    with far more reports than outlets — sixty items from ten publishers — is
    not a very big story; it is a chain of loosely linked ones. So is anything
    past the size that the day's whole press corps could plausibly produce.
    """
    n = len(cluster.items)
    if n < 6:
        return False
    outlets = len(cluster.source_slugs) or n
    return n > 2 * outlets or n >= 24


def split_incoherent(cluster: Cluster, linked) -> list[Cluster]:
    """Break a cluster that was only ever held together by a chain.

    Both merging passes are single-link: A joins B, B joins C, and nothing
    ever asked whether A has anything to do with C. Most of the time that is
    right — a foreign outlet words an event differently from four domestic
    ones and hangs on by a single link — so ordinary clusters are left exactly
    as they are. But one loose link is enough to weld two stories together,
    and on a busy day a few of them weld forty. The card for that cluster
    would list forty sources for a headline most of them never reported, which
    is the precise failure a source list exists to prevent.

    A cluster that :func:`looks_welded` is therefore re-read as a graph of
    direct links and cut into stars: the report tied to most others, the
    reports tied directly to it, and any report tied to at least half of that
    group. A leftover of one or two reports rejoins the single group it is
    most tied to, so a legitimately odd wording is not orphaned.
    """
    if not looks_welded(cluster):
        return [cluster]

    items = cluster.items
    n = len(items)
    adjacent: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if linked(items[i], items[j]):
                adjacent[i].add(j)
                adjacent[j].add(i)

    remaining = set(range(n))
    groups: list[set[int]] = []
    while remaining:
        hub = max(remaining, key=lambda k: (len(adjacent[k] & remaining), -k))
        group = {hub} | (adjacent[hub] & remaining)
        grew = True
        while grew:
            grew = False
            for k in sorted(remaining - group):
                if len(adjacent[k] & group) * 2 >= len(group):
                    group.add(k)
                    grew = True
        groups.append(group)
        remaining -= group

    # Tails: a stray report or pair goes back to the one group it leans on.
    anchors = [g for g in groups if len(g) >= 3]
    settled: list[set[int]] = list(anchors)
    for tail in (g for g in groups if len(g) < 3):
        ties = [sum(len(adjacent[k] & anchor) for k in tail) for anchor in anchors]
        best = max(ties, default=0)
        if best and ties.count(best) == 1:
            anchors[ties.index(best)].update(tail)
        else:
            settled.append(tail)

    if len(settled) == 1:
        return [cluster]
    return [_make_cluster([items[i] for i in sorted(group)]) for group in settled]


@dataclass
class Evidence:
    """Why two reports are, or are not, taken to describe one event."""

    shared: set[str] = field(default_factory=set)
    shared_headline: set[str] = field(default_factory=set)
    shared_numbers: set[str] = field(default_factory=set)
    containment: float = 0.0        # weighted share of the smaller report's terms
    headline_containment: float = 0.0
    rule: str = ""

    @property
    def same_event(self) -> bool:
        return bool(self.rule)


def same_event_evidence(a: ClusterItem, b: ClusterItem) -> Evidence:
    """Decide from two reports alone whether they describe the same event.

    The first pass asks whether two reports are worded alike. This one asks a
    different question — do they name the same specific things? — because
    outlets word one event very differently ("RBI keeps repo rate unchanged",
    "Repo rate stays at 6.5% as MPC holds") while still agreeing on the terms
    that matter.

    Three properties are deliberate, each the fix for a way this went wrong:

    * It is judged pair by pair. An earlier version pooled the rare words of a
      whole cluster, so every merge widened the net for the next one and
      unrelated stories snowballed together.
    * Terms are weighted by how rare they are in the batch instead of passing
      a rarity cut-off, so a busy day does not turn "police" and "court" into
      evidence.
    * The two *headlines* must share specific terms. A second story about the
      same person shares the name and nothing else; without this rule "Trump
      pledges $1 million reward" and "Trump criticises Brazil election" are
      one story, and the card for it attributes each to the other.
    * "Specific" is measured against the batch. Only headline terms that few
      of the day's reports use are counted, so the three words of "Reserve Bank
      of India" in two headlines do not add up to agreement on a day when the
      bank is in the news eight separate times.
    """
    evidence = Evidence()
    if not a.evidence or not b.evidence:
        return evidence

    evidence.shared = a.evidence & b.evidence
    evidence.shared_headline = a.head_specific & b.head_specific
    evidence.shared_numbers = {
        n for n in set(a.numbers) & set(b.numbers) if len(n) >= 3
    }

    def weight(terms: set[str], item: ClusterItem) -> float:
        return sum(item.evidence_weight.get(t, 1.0) for t in terms)

    smaller = min(weight(a.evidence, a), weight(b.evidence, b))
    if smaller > 0:
        shared_weight = min(weight(evidence.shared, a), weight(evidence.shared, b))
        evidence.containment = shared_weight / smaller
    shortest_headline = min(len(a.head_specific), len(b.head_specific))
    if shortest_headline:
        evidence.headline_containment = len(evidence.shared_headline) / shortest_headline

    n_head = len(evidence.shared_headline)
    if n_head >= 3 and evidence.headline_containment >= 0.6:
        evidence.rule = "headlines agree"
    elif n_head >= 2 and evidence.containment >= 0.40 and len(evidence.shared) >= 3:
        evidence.rule = "shared specifics"
    elif evidence.shared_numbers and n_head >= 1 and evidence.containment >= 0.30:
        evidence.rule = "shared figure"
    elif evidence.containment >= 0.62 and len(evidence.shared) >= 5 and n_head >= 1:
        evidence.rule = "same account"
    return evidence


EVIDENCE_LEXICAL_FLOOR = 0.08


def merge_on_shared_evidence(
    clusters: list[Cluster],
    *,
    window_hours: int,
    lexical_floor: float = EVIDENCE_LEXICAL_FLOOR,
) -> list[Cluster]:
    """Second pass: join clusters when two of their reports name the same event.

    A merge needs a *pair of reports*, one from each cluster, that pass
    :func:`same_event_evidence`. Nothing is pooled across a cluster, so joining
    two clusters does not make either of them easier to join again.

    Every rule in that test needs the two headlines to share a specific term,
    so an index from term to reports proposes the only pairs worth reading.
    Comparing every cluster with every other, and starting over after each
    merge, is correct and takes minutes on a full day's news; this takes
    seconds and reaches the same pairs.
    """
    if len(clusters) < 2:
        return clusters

    flat: list[ClusterItem] = []
    owner: list[int] = []
    for index, cluster in enumerate(clusters):
        for item in cluster.items:
            flat.append(item)
            owner.append(index)

    parent = list(range(len(clusters)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cities: list[set[str]] = [c.cities for c in clusters]
    latest: list[datetime | None] = [c.latest for c in clusters]
    window = timedelta(hours=window_hours)

    postings: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(flat):
        for term in item.head_specific:
            postings[term].append(index)

    examined: set[tuple[int, int]] = set()
    for term in sorted(postings):
        indexes = postings[term]
        for p in range(len(indexes)):
            for q in range(p + 1, len(indexes)):
                i, j = indexes[p], indexes[q]
                if (i, j) in examined:
                    continue
                examined.add((i, j))
                ra, rb = find(owner[i]), find(owner[j])
                if ra == rb:
                    continue
                x, y = flat[i], flat[j]
                if not _within_window(x, y, window_hours):
                    continue
                la, lb = latest[ra], latest[rb]
                if la and lb and abs(la - lb) > window:
                    continue
                # Same city guard as the primary pass, held at cluster level:
                # a report naming no city must not smuggle a Mumbai story into
                # a Delhi one.
                if cities[ra] and cities[rb] and not (cities[ra] & cities[rb]):
                    continue
                if lexical_similarity(x.vector, y.vector) < lexical_floor:
                    continue
                if not same_event_evidence(x, y).same_event:
                    continue
                parent[rb] = ra
                cities[ra] = cities[ra] | cities[rb]
                latest[ra] = max(la, lb) if la and lb else (la or lb)

    grouped: dict[int, list[ClusterItem]] = defaultdict(list)
    for index, cluster in enumerate(clusters):
        grouped[find(index)].extend(cluster.items)
    return [_make_cluster(members) for members in grouped.values() if members]


def best_matching_cluster(
    item: ClusterItem,
    clusters: list[Cluster],
    *,
    threshold: float | None = None,
    window_hours: int | None = None,
) -> tuple[Cluster | None, float]:
    """Assign a newly arrived article to an existing open cluster, if any."""
    settings = get_settings()
    threshold = settings.cluster_similarity_threshold if threshold is None else threshold
    window_hours = settings.cluster_time_window_hours if window_hours is None else window_hours

    best: Cluster | None = None
    best_score = 0.0
    for cluster in clusters:
        latest = cluster.latest
        if (
            latest
            and item.published_at
            and abs(item.published_at - latest) > timedelta(hours=window_hours)
        ):
            continue
        lexical = lexical_similarity(item.vector, cluster.centroid_vector)
        ent = 0.0
        if cluster.entity_keys and item.entity_keys:
            inter = len(cluster.entity_keys & item.entity_keys)
            ent = inter / min(len(cluster.entity_keys), len(item.entity_keys))
        score = composite_similarity(lexical, ent, 0.0)
        if score > best_score:
            best, best_score = cluster, score
    if best is not None and best_score >= threshold:
        return best, best_score
    return None, best_score
