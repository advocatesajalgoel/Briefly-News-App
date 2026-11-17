"""Deterministic, credential-free extraction.

This is a real extractor, not a stub: it reads the syndicated headline and
blurb, segments them, and fills the who/what/when/where/why slots plus numbers,
dates and attribution using linguistic cues. Two things make it trustworthy
rather than merely cheap:

* every fact keeps the verbatim ``evidence`` span it came from, so the grounding
  check downstream is a lookup rather than a judgement call;
* nothing is upgraded to ``confirmed`` here — that only happens when several
  independent sources, or an official one, carry the same fact.
"""

from __future__ import annotations

import re
from collections import defaultdict

from app.llm.schema import ExtractionProvider, ExtractionResult, FactCandidate, SourceDocument
from app.text.gazetteer import PLACES  # noqa: F401
from app.text.gazetteer import is_place as _is_place
from app.text.normalize import (
    clean_text,
    entity_key,
    extract_dates,
    extract_entities,
    extract_numbers,
    tokenize,
)
from app.text.similarity import entities_match
from app.text.style_guard import (
    CONFIRMATION_TERMS,
    SPECULATION_MARKERS,
    neutralise,
)
from app.text.wordcount import count_words, normalise_whitespace, split_sentences

_ATTRIBUTION_VERB = re.compile(
    r"\b(said|says|stated|told|announced|confirmed|added|noted|claimed|claims|"
    r"alleged|alleges|denied|denies|argued|warned|urged|reported|writes)\b",
    re.IGNORECASE,
)
_ACCORDING_TO = re.compile(r"\baccording to ([A-Z][^,.;]{2,60})", re.IGNORECASE)
_WHY_MARKER = re.compile(
    r"\b(?:because|after|following|amid|citing|due to|owing to|in response to|"
    r"as part of|over)\b\s+(.{6,120}?)(?=[,;]|\.\s|\.$|$)",
    re.IGNORECASE,
)
_QUOTE_RE = re.compile(r"[“\"]([^”\"]{10,240})[”\"]")
_BARE_YEAR = re.compile(r"(?:19|20)\d{2}")
# "... Donald Trump on Monday [announced]": the day is when, not who.
_TRAILING_TIME = re.compile(
    r"\s+(?:on\s+)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|"
    r"today|yesterday|earlier|later|recently|also|has|had|have|further)\s*$",
    re.IGNORECASE,
)

# A dispute is somebody contesting a *claim*. "The court rejected the plea",
# "police questioned the suspect" and "he was denied bail" contain the same
# verbs and are nothing of the kind, so the bare verbs are not enough: each one
# has to be aimed at an account, a figure or an allegation.
_CLAIM_NOUN = (
    r"(?:claims?|allegations?|charges?|accusations?|reports?|account|version|"
    r"figures?|numbers?|data|findings?|assertion|narrative|suggestion|statement|"
    r"estimate|projection|tally|toll|results?)"
)
_DISPUTE_RE = re.compile(
    r"(?<![\w])(?:"
    r"disput(?:ed|es|ing)\b(?!\s+(?:land|territory|border|region|area|site|structure|"
    r"property|plot|waters|island|islands))"
    r"|den(?:ied|ies|ying)\b(?!\s+(?:bail|permission|entry|visa|access|parole|admission|"
    r"boarding|a\b|an\b|the\s+(?:request|plea|application|petition)))"
    r"|refut(?:ed|es|ing)\b|contradict(?:ed|s|ing)\b|push(?:ed|es|ing)\s+back\b"
    r"|(?:reject(?:ed|s|ing)|contest(?:ed|s|ing)|question(?:ed|s|ing)|challeng(?:ed|es|ing))"
    r"\s+(?:(?:the|these|those|that|this|his|her|its|their|such|any|all)\s+)?"
    r"(?:\w+\s+){0,2}" + _CLAIM_NOUN + r"\b"
    r"|conflicting\s+" + _CLAIM_NOUN + r"\b"
    r"|no\s+independent\s+confirmation\b|could\s+not\s+be\s+(?:independently\s+)?verified\b"
    r"|unverified\b|differs?\s+from\b"
    r")",
    re.IGNORECASE,
)
_CONFIRM_RE = re.compile(
    r"(?<![\w])(?:"
    + "|".join(sorted((re.escape(t) for t in CONFIRMATION_TERMS), key=len, reverse=True))
    + r")(?![\w])",
    re.IGNORECASE,
)
_HEDGE_RE = re.compile(
    r"(?<![\w])(?:"
    + "|".join(sorted((re.escape(t) for t in SPECULATION_MARKERS), key=len, reverse=True))
    + r")(?![\w])",
    re.IGNORECASE,
)

# Furniture publishers bolt onto headlines that is not part of the event.
_HEADLINE_NOISE = re.compile(
    r"^(breaking|update|exclusive|watch|live|video|photos?|opinion|analysis|"
    r"explained|big story|top news|just in)\s*[:\-–|]\s*",
    re.IGNORECASE,
)
# " - The Hindu", " | NDTV": a separator standing between spaces, then a name.
# The spaces are the point. Without them "After Anti-Dam Protests" loses its
# last two words to a brand that was never there.
_TRAILING_SEGMENT = re.compile(r"\s+[|\-–—]\s+(?P<tail>[^|\-–—]{2,48})$")
_BRAND_WORDS = {
    "news", "times", "post", "express", "today", "tv", "network", "tribune",
    "herald", "hindu", "mint", "standard", "chronicle", "journal", "daily",
    "wire", "guardian", "bbc", "ndtv", "reuters", "ani", "pti", "ians",
    "online", "live", "world", "india", "business", "sports", "cricket",
}
_BRAND_GLUE = {"of", "the", "and", "&"}


def _looks_like_brand(tail: str, publisher: str | None) -> bool:
    """Is the text after the last separator a masthead rather than the story?

    "India beat Australia - Kohli hits century" ends in news; "Rate held at
    6.25% - The Hindu" ends in a name. Only the second may be cut.
    """
    tail = tail.strip()
    if publisher:
        a, b = tail.lower(), publisher.lower()
        if a == b or a in b or b in a:
            return True
    if tail.lower().endswith((".com", ".in", ".co.uk", ".org")):
        return True
    words = tail.split()
    if not 1 <= len(words) <= 5:
        return False
    if not all(w[:1].isupper() or w.lower() in _BRAND_GLUE for w in words):
        return False
    return any(w.lower().strip(".,") in _BRAND_WORDS for w in words)


def clean_headline(headline: str, publisher: str | None = None) -> str:
    """Remove publisher furniture from the ends of a headline. Nothing else.

    The words of the headline itself are never changed: it is shown on the card
    as that outlet's own headline.
    """
    text = clean_text(headline)
    text = _HEADLINE_NOISE.sub("", text)
    for _ in range(2):  # "Headline | Section - Outlet"
        match = _TRAILING_SEGMENT.search(text)
        if not match or not _looks_like_brand(match.group("tail"), publisher):
            break
        text = text[: match.start()]
    return text.strip(" -–—|:")


def _speaker_before_verb(sentence: str) -> str | None:
    """Find who is speaking in ``X said …`` and ``…, an official said``.

    The phrase immediately before the verb is the speaker, so the segment after
    the final comma is checked first. Taking the whole clause instead would make
    the subject of the sentence the "speaker" — which is how you end up
    attributing "work is expected to begin in November" to somebody called Work.
    """
    m = _ATTRIBUTION_VERB.search(sentence)
    if not m:
        return None
    head = sentence[: m.start()].strip(" ,;:")
    if not head:
        tail = sentence[m.end():].strip(" ,;:")
        ents = extract_entities(tail)
        return ents[0] if ents else None

    segment = _TRAILING_TIME.sub("", head.rsplit(",", 1)[-1]).strip(" ,;:")
    if segment and 0 < count_words(segment) <= 6:
        return segment
    ents = extract_entities(head)
    if ents:
        return ents[-1]
    return head if 0 < count_words(head) <= 6 else None


class RuleBasedProvider(ExtractionProvider):
    name = "rule_based"

    def available(self) -> bool:
        return True

    # -- per document ----------------------------------------------------
    def _facts_from_document(self, doc: SourceDocument) -> list[FactCandidate]:
        facts: list[FactCandidate] = []
        headline = clean_headline(doc.headline)
        body = clean_text(doc.summary)
        material = f"{headline}. {body}".strip()
        if not headline:
            return facts

        entities = extract_entities(material)
        actors = [e for e in entities if not _is_place(e)]
        places = [e for e in entities if _is_place(e)]

        def add(**kw) -> None:
            facts.append(
                FactCandidate(
                    source_index=doc.index, source_slug=doc.source_slug, **kw
                ).normalised()
            )

        # WHAT — the event itself, taken from the headline with publisher
        # furniture and loaded verbs removed. Kept as the anchor of the story.
        add(
            slot="what",
            kind="attributed",
            text=neutralise(headline),
            evidence=doc.headline,
            attributed_to=doc.source_name,
            confidence=0.6,
            salience=1.0,
            extra={"from_headline": True},
        )

        # WHO — the actors named, most prominent first.
        for i, actor in enumerate(actors[:4]):
            add(
                slot="who",
                kind="context",
                text=actor,
                evidence=actor,
                confidence=0.6,
                salience=max(0.3, 0.9 - 0.15 * i),
            )

        # WHERE
        for i, place in enumerate(places[:3]):
            add(
                slot="where",
                kind="context",
                text=place,
                evidence=place,
                confidence=0.7,
                salience=max(0.2, 0.7 - 0.15 * i),
            )

        # WHEN — explicit date expressions plus the publication stamp.
        # A bare year is not when something happened: "the 2028 deadline" and
        # "Mission 2027" name a deadline and a campaign, and a card that ends
        # ", on 2028" is reporting a date nobody gave.
        dated = [d for d in extract_dates(material) if not _BARE_YEAR.fullmatch(d)]
        for i, date in enumerate(dated[:3]):
            add(
                slot="when",
                kind="date",
                text=date,
                evidence=date,
                confidence=0.7,
                salience=max(0.2, 0.6 - 0.15 * i),
            )

        # NUMBERS — excluding figures that are part of a date expression, which
        # the `when` slot already carries ("12 December" is not a quantity).
        date_text = " ".join(extract_dates(material)).lower()
        numbers = [n for n in extract_numbers(material) if n.lower() not in date_text]
        for i, number in enumerate(numbers[:5]):
            context = _snippet_around(material, number)
            add(
                slot="number",
                kind="number",
                text=number,
                evidence=context or number,
                confidence=0.75,
                salience=max(0.3, 0.85 - 0.1 * i),
                extra={"context": context},
            )

        # WHY
        for m in list(_WHY_MARKER.finditer(material))[:2]:
            reason = normalise_whitespace(m.group(0))
            if count_words(reason) < 3:
                continue
            add(
                slot="why",
                kind="context",
                text=neutralise(reason),
                evidence=m.group(0),
                confidence=0.5,
                salience=0.55,
            )

        # Attribution, dispute, confirmation, hedging — sentence by sentence.
        for sentence in split_sentences(material):
            speaker = None
            am = _ACCORDING_TO.search(sentence)
            if am:
                speaker = clean_text(am.group(1))
            if speaker is None:
                speaker = _speaker_before_verb(sentence)

            is_dispute = bool(_DISPUTE_RE.search(sentence))
            is_confirm = bool(_CONFIRM_RE.search(sentence))
            is_hedged = bool(_HEDGE_RE.search(sentence))

            if is_dispute:
                add(
                    slot="what",
                    kind="disputed",
                    text=neutralise(sentence),
                    attributed_to=speaker or doc.source_name,
                    evidence=sentence,
                    confidence=0.5,
                    salience=0.8,
                )
            elif speaker and _ATTRIBUTION_VERB.search(sentence):
                add(
                    slot="what",
                    kind="attributed",
                    text=neutralise(sentence),
                    attributed_to=speaker,
                    evidence=sentence,
                    confidence=0.6,
                    salience=0.7,
                )
            elif is_confirm:
                add(
                    slot="what",
                    kind="attributed",
                    text=neutralise(sentence),
                    attributed_to=doc.source_name,
                    evidence=sentence,
                    confidence=0.65,
                    salience=0.65,
                    extra={"confirmation_language": True},
                )
            elif is_hedged:
                add(
                    slot="what",
                    kind="uncertain",
                    text=neutralise(sentence),
                    attributed_to=doc.source_name,
                    evidence=sentence,
                    confidence=0.35,
                    salience=0.4,
                )

            for q in _QUOTE_RE.findall(sentence):
                add(
                    slot="other",
                    kind="attributed",
                    text=q.strip(),
                    attributed_to=speaker or doc.source_name,
                    evidence=q,
                    confidence=0.7,
                    salience=0.5,
                    extra={"is_quote": True},
                )

        return facts

    # -- across the cluster ----------------------------------------------
    def extract(self, documents: list[SourceDocument]) -> ExtractionResult:
        result = ExtractionResult(provider=self.name)
        if not documents:
            result.warnings.append("no documents supplied")
            return result

        all_facts: list[FactCandidate] = []
        for doc in documents:
            all_facts.extend(self._facts_from_document(doc))

        result.facts = merge_facts(all_facts, documents)
        result.headline = build_neutral_headline(documents, result.facts)
        result.facts = _add_event_fact(result.facts, documents, result.headline)
        result.dek = build_dek(result.facts, documents)
        result.summary_clauses = build_summary_clauses(
            result.facts, documents, result.headline
        )
        return result

    def write_narration(self, story_brief: dict, target_words: int, mode: str = "daily") -> str:
        # The rule-based narrator lives in app/podcast/narrator.py so the hosted
        # providers and this one share the same paragraph plan.
        from app.podcast.narrator import compose_narration

        return compose_narration(story_brief, target_words=target_words, mode=mode)


# --- helpers ---------------------------------------------------------------


def _snippet_around(text: str, needle: str, width: int = 60) -> str:
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return ""
    start = max(0, idx - width)
    end = min(len(text), idx + len(needle) + width)
    return normalise_whitespace(text[start:end])


def _fact_signature(fact: FactCandidate) -> str:
    if fact.slot in {"who", "where"}:
        return f"{fact.slot}:{entity_key(fact.text)}"
    if fact.slot in {"number", "date"}:
        compact = re.sub(r"\s+", "", fact.text.lower())
        return f"{fact.slot}:{compact}"
    toks = tokenize(fact.text)
    return f"{fact.slot}:{fact.kind}:" + " ".join(sorted(set(toks))[:12])


def merge_facts(
    facts: list[FactCandidate], documents: list[SourceDocument]
) -> list[FactCandidate]:
    """Collapse duplicates and count how many *independent* sources back each fact."""
    by_index = {d.index: d for d in documents}
    groups: dict[str, list[FactCandidate]] = defaultdict(list)
    for fact in facts:
        groups[_fact_signature(fact)].append(fact)

    merged: list[FactCandidate] = []
    for group in groups.values():
        best = max(group, key=lambda f: (f.salience, f.confidence, -count_words(f.text)))
        slugs = {f.source_slug for f in group if f.source_slug}
        support = len(slugs) or 1
        kinds = {f.kind for f in group}

        kind = best.kind
        official = any(
            by_index.get(f.source_index) and by_index[f.source_index].source_kind == "official"
            for f in group
        )
        if "disputed" in kinds:
            kind = "disputed"
        elif kind in {"attributed", "context"} and (support >= 2 or official):
            # Independently corroborated, or stated by a primary source.
            kind = "confirmed" if best.slot in {"what", "who", "where"} else kind

        confidence = min(0.98, best.confidence + 0.12 * (support - 1) + (0.15 if official else 0))
        merged.append(
            FactCandidate(
                slot=best.slot,
                kind=kind,
                text=best.text,
                attributed_to=best.attributed_to,
                evidence=best.evidence,
                source_index=best.source_index,
                source_slug=best.source_slug,
                support_count=support,
                confidence=confidence,
                salience=min(1.0, best.salience + 0.05 * (support - 1)),
                extra={**best.extra, "supporting_sources": sorted(slugs), "official": official},
            ).normalised()
        )

    merged = _merge_similar_narrative_facts(merged)
    merged.sort(key=lambda f: (-f.salience, -f.support_count, -f.confidence))
    return merged


def _merge_similar_narrative_facts(facts: list[FactCandidate]) -> list[FactCandidate]:
    """Two publishers rarely word the same event identically.

    Exact-signature merging therefore under-counts agreement, which would make a
    story look less corroborated than it is. This second pass joins narrative
    facts whose content words substantially overlap.
    """
    narrative = [f for f in facts if f.slot in {"what", "why"}]
    others = [f for f in facts if f.slot not in {"what", "why"}]

    groups: list[list[FactCandidate]] = []
    token_sets: list[set[str]] = []
    for fact in narrative:
        toks = set(tokenize(fact.text))
        placed = False
        for gi, existing in enumerate(token_sets):
            if not existing or not toks:
                continue
            overlap = len(existing & toks) / min(len(existing), len(toks))
            if overlap >= 0.55:
                groups[gi].append(fact)
                token_sets[gi] = existing | toks
                placed = True
                break
        if not placed:
            groups.append([fact])
            token_sets.append(toks)

    out: list[FactCandidate] = list(others)
    for group in groups:
        if len(group) == 1:
            out.append(group[0])
            continue
        slugs: set[str] = set()
        for f in group:
            slugs |= set((f.extra or {}).get("supporting_sources") or [])
            if f.source_slug:
                slugs.add(f.source_slug)
        kinds = {f.kind for f in group}
        official = any((f.extra or {}).get("official") for f in group)
        # Prefer the most informative wording among the agreeing versions.
        best = max(group, key=lambda f: (f.support_count, count_words(f.text), f.confidence))
        kind = "disputed" if "disputed" in kinds else best.kind
        if kind in {"attributed", "context"} and (len(slugs) >= 2 or official):
            kind = "confirmed"
        out.append(
            FactCandidate(
                slot=best.slot,
                kind=kind,
                text=best.text,
                attributed_to=best.attributed_to,
                evidence=best.evidence,
                source_index=best.source_index,
                source_slug=best.source_slug,
                support_count=max(len(slugs), 1),
                confidence=min(0.98, best.confidence + 0.1 * (len(slugs) - 1)),
                salience=min(1.0, best.salience + 0.05 * (len(slugs) - 1)),
                extra={**best.extra, "supporting_sources": sorted(slugs), "official": official},
            ).normalised()
        )
    return out


def _add_event_fact(
    facts: list[FactCandidate], documents: list[SourceDocument], headline: str
) -> list[FactCandidate]:
    """Record "this event was reported by N sources" as one fact.

    Clustering has already established that these documents describe the same
    event, so the event itself is corroborated by every distinct publisher in
    the cluster — even though each of them worded its headline differently.
    Individual headline paraphrases are dropped in favour of this single row so
    the fact set does not double-count the same claim.
    """
    slugs = {d.source_slug for d in documents if d.source_slug}
    official = any(d.source_kind == "official" for d in documents)
    kind = "confirmed" if (len(slugs) >= 2 or official) else "attributed"
    attributed_to = None if kind == "confirmed" else (documents[0].source_name if documents else None)

    event = FactCandidate(
        slot="what",
        kind=kind,
        text=headline.rstrip("."),
        attributed_to=attributed_to,
        evidence=documents[0].headline if documents else None,
        source_index=documents[0].index if documents else None,
        source_slug=documents[0].source_slug if documents else None,
        support_count=max(len(slugs), 1),
        confidence=min(0.95, 0.6 + 0.1 * len(slugs) + (0.15 if official else 0.0)),
        salience=1.0,
        extra={"is_event": True, "supporting_sources": sorted(slugs), "official": official},
    ).normalised()

    kept = [f for f in facts if not (f.extra or {}).get("from_headline")]
    return [event, *kept]


def build_neutral_headline(
    documents: list[SourceDocument], facts: list[FactCandidate]
) -> str:
    """Pick the plainest headline available and strip it back.

    Briefly does not paraphrase a headline into something the sources did not
    say; it selects the least loaded formulation among them and removes
    publisher furniture. The publishers' own headlines stay visible, verbatim,
    in the sources list.
    """
    from app.text.style_guard import check

    # Content words that the cluster actually agrees on.
    agreed: set[str] = set()
    for fact in facts:
        if fact.support_count >= 2 or fact.kind == "confirmed":
            agreed |= set(tokenize(fact.text))

    candidates: list[tuple[float, str]] = []
    for doc in documents:
        headline = clean_headline(doc.headline)
        if not headline:
            continue
        report = check(headline, require_attribution_for_allegations=False)
        penalty = sum(3.0 if f.severity == "blocker" else 1.0 for f in report.findings)
        toks = set(tokenize(headline))
        length = count_words(headline)
        # Reward saying more of what the sources agree on; punish drifting away
        # from the ideal card headline length in either direction.
        coverage = (len(toks & agreed) / len(agreed)) if agreed else 0.0
        specificity = min(len(toks), 10) / 10.0
        length_penalty = abs(length - 11) * 0.18
        kind_bonus = {"wire": -0.6, "international": -0.2}.get(doc.source_kind, 0.0)
        score = penalty + length_penalty + kind_bonus - 2.0 * coverage - 1.0 * specificity
        candidates.append((score, headline))
    if not candidates:
        what = next((f.text for f in facts if f.slot == "what"), "")
        return what or "Untitled story"
    candidates.sort(key=lambda c: c[0])
    return neutralise(candidates[0][1])


def build_dek(facts: list[FactCandidate], documents: list[SourceDocument]) -> str:
    """A two-sentence neutral standfirst used by the Deep Dive narrator."""
    parts: list[str] = []
    confirmed = [f for f in facts if f.kind == "confirmed" and f.slot == "what"]
    attributed = [f for f in facts if f.kind == "attributed" and f.slot == "what"]
    disputed = [f for f in facts if f.kind == "disputed"]
    if confirmed:
        parts.append(confirmed[0].text.rstrip("."))
    elif attributed:
        first = attributed[0]
        who = first.attributed_to or "the source"
        parts.append(f"{who} said {first.text[0].lower() + first.text[1:]}".rstrip("."))
    if disputed:
        parts.append(
            f"{disputed[0].attributed_to or 'One source'} disputed part of this account"
        )
    if not parts:
        return ""
    return ". ".join(p.strip().rstrip(".") for p in parts) + "."


_EDGE_JUNK = {"the", "a", "an", "of", "to", "in", "on", "at", "for", "and", "or",
              "with", "by", "from", "as", "that", "which", "is", "are", "was",
              "were", "said", "says", "will", "its"}


def _trim_edges(words: list[str]) -> list[str]:
    """Drop function words that end up stranded at either end of a fragment."""
    while words and words[0].lower().strip(".,;:") in _EDGE_JUNK:
        words.pop(0)
    while words and words[-1].lower().strip(".,;:") in _EDGE_JUNK:
        words.pop()
    return words


_ATTRIBUTION_FRAME = re.compile(
    r"^(?P<speaker>[A-Z][^,.;]{1,60}?)\s+"
    r"(?:said|says|told|announced|confirmed|added|noted|stated|reported|claimed|alleged)"
    r"\s+(?:that\s+)?(?P<body>.+)$"
)
_ACCORDING_FRAME = re.compile(r"^According to (?P<speaker>[^,]{2,60}),\s*(?P<body>.+)$", re.I)
_TRAILING_ATTRIBUTION = re.compile(
    r",\s*(?:(?:the\s+)?[a-z][\w\s]{0,40}\s)?"
    r"(?:said|says|told|announced|confirmed|added|stated|reported)\s*$",
    re.IGNORECASE,
)
_LEADING_DETERMINER = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)


def split_attribution(text: str) -> tuple[str | None, str]:
    """Separate "X said that Y" into ("X", "Y").

    Moving the attribution out of the front and re-attaching it at the end does
    three useful things at once: it stops the same speaker being named twice, it
    puts the fact first where a 30-word card needs it, and it breaks up the long
    verbatim runs that the copying check (rightly) objects to.
    """
    text = normalise_whitespace(text).rstrip(".")
    if not text:
        return None, ""
    explicit = _ACCORDING_FRAME.match(text)
    match = explicit or _ATTRIBUTION_FRAME.match(text)
    if not match:
        return None, text
    speaker = normalise_whitespace(match.group("speaker")).strip(" ,")
    body = normalise_whitespace(match.group("body")).strip(" ,")
    # "According to X, ..." is unambiguous, so a short remainder is fine. The
    # bare "X said ..." form is not: requiring a few words after it stops a
    # sentence being mistaken for an attribution frame.
    minimum = 2 if explicit else 3
    if not body or count_words(body) < minimum:
        return None, text
    body = _TRAILING_ATTRIBUTION.sub("", body).strip(" ,")
    return speaker or None, body


CORE_CLAUSE_MAX_WORDS = 14
# Words that mark the start of a phrase we would rather cut before than through.
_BOUNDARY_WORDS = {"in", "on", "at", "from", "with", "after", "before", "during",
                   "into", "over", "under", "through", "by", "for", "to",
                   "against", "amid", "citing", "following", "because", "while"}


# Openers that are safe to down-case when a fragment is spliced mid-sentence.
# Anything else keeps its capital, so "in August" never becomes "in august" and
# "Reserve Bank" never becomes "reserve Bank".
_SAFE_LOWER_OPENERS = {
    "the", "a", "an", "this", "that", "these", "those", "it", "its", "his",
    "her", "their", "there", "after", "following", "because", "amid", "citing",
    "over", "due", "owing", "since", "while", "work", "officials", "police",
    "authorities", "several", "many", "more", "no", "two", "three", "four",
    "five", "wind", "power", "relief", "shares", "prices", "talks", "traffic",
}


def _soft_lower(text: str) -> str:
    if not text:
        return text
    first = text.split(" ", 1)[0].strip("\"'“”‘’()")
    if first.lower() in _SAFE_LOWER_OPENERS and first[1:].islower():
        return text[0].lower() + text[1:]
    return text


def _core_statement(text: str, max_words: int = CORE_CLAUSE_MAX_WORDS) -> str:
    """Trim a sentence back to the claim it makes.

    The cap matters for more than length. A card whose whole summary is one long
    span of a publisher's sentence is copying, however short it is; capping the
    core and letting the other slots fill the budget means the card is assembled
    from several places, which is what it should have been all along.
    """
    text = _TRAILING_ATTRIBUTION.sub("", normalise_whitespace(text).rstrip(".")).strip(" ,")
    text = _LEADING_DETERMINER.sub("", text)
    if count_words(text) > max_words:
        words = text.split()[:max_words]
        joined = " ".join(words)
        # Everything after a comma is usually a where/when/why tail that the
        # other slots pick up on their own.
        if "," in joined:
            joined = joined.rsplit(",", 1)[0]
        # Cut before a trailing prepositional phrase rather than mid-phrase, so
        # the fragment ends on the verb: "will lift off", not "in a window
        # opening".
        parts = joined.split()
        for cut in range(len(parts) - 1, max(2, len(parts) - 7), -1):
            if parts[cut].lower() in _BOUNDARY_WORDS:
                parts = parts[:cut]
                break
        text = " ".join(_trim_edges(parts))
    return text[0].upper() + text[1:] if text else text


def build_summary_clauses(
    facts: list[FactCandidate],
    documents: list[SourceDocument],
    headline: str = "",
) -> list[dict]:
    """Ranked clause candidates for the 30-word card.

    This only proposes; :mod:`app.pipeline.summarize` deduplicates and the word
    budget decides what survives. Clauses are fragments assembled from different
    facts rather than one lifted sentence, which is both the honest way to build
    a summary from extracted information and what keeps the card from reading as
    a copy of any single publisher.
    """
    clauses: list[dict] = []
    headline_tokens = set(tokenize(headline))
    publisher_names = {d.source_name.lower() for d in documents}

    def _what_score(f: FactCandidate) -> tuple:
        toks = set(tokenize(f.text))
        redundancy = (
            len(toks & headline_tokens) / len(toks) if toks and headline_tokens else 0.0
        )
        confirmed_bonus = 1.0 if f.kind == "confirmed" else 0.0
        return (
            confirmed_bonus + min(f.support_count, 4) - 4.0 * redundancy + 0.5 * f.salience,
            len(toks),
        )

    what_candidates = [f for f in facts if f.slot == "what" and f.kind != "disputed"]
    # The event fact *is* the headline; only fall back to it if nothing else
    # adds detail beyond what the reader has already read.
    detail = [f for f in what_candidates if not (f.extra or {}).get("is_event")]
    pool = detail or what_candidates
    what = max(pool, key=_what_score) if pool else None

    speaker: str | None = None
    if what is not None:
        speaker, body = split_attribution(what.text)
        if speaker is None and what.kind == "attributed":
            speaker = what.attributed_to
        core = _core_statement(body)
        if core:
            clauses.append({"text": core, "priority": 100, "required": True, "slot": "what"})
        # Attribution rides at the end, and only when it names somebody other
        # than the publisher — "The Hindu said" tells a reader nothing they
        # cannot see in the source list.
        if speaker and speaker.lower() not in publisher_names:
            spoken = speaker
            # "The monetary committee said" mid-sentence keeps its determiner
            # lower-case; a name keeps its capital.
            if spoken.split()[0] in {"The", "A", "An"}:
                spoken = spoken[0].lower() + spoken[1:]
            clauses.append(
                {"text": f", {spoken} said", "priority": 74, "required": False,
                 "slot": "attribution"}
            )

    # Only surface a figure the reader has not already been given. Repeating
    # "6.25 per cent" from the core clause costs words and adds nothing.
    core_text = clauses[0]["text"].lower() if clauses else ""
    number = next(
        (
            f
            for f in facts
            if f.slot == "number" and f.text.lower() not in core_text
        ),
        None,
    )
    if number is not None:
        ctx = (number.extra or {}).get("context") or ""
        clauses.append(
            {"text": _number_label(ctx, number.text), "priority": 70, "required": False,
             "slot": "number"}
        )

    where = next((f for f in facts if f.slot == "where"), None)
    if where is not None and where.text.lower() not in (what.text.lower() if what else ""):
        clauses.append({"text": f"in {where.text}", "priority": 62, "required": False,
                        "slot": "where"})

    when = next((f for f in facts if f.slot == "when"), None)
    if when is not None:
        clauses.append({"text": f"on {when.text}" if _needs_on(when.text) else when.text,
                        "priority": 55, "required": False, "slot": "when"})

    why = next((f for f in facts if f.slot == "why"), None)
    if why is not None:
        clauses.append({"text": _soft_lower(_core_statement(why.text)), "priority": 48,
                        "required": False, "slot": "why"})

    disputed = next((f for f in facts if f.kind == "disputed"), None)
    if disputed is not None:
        who, _ = split_attribution(disputed.text)
        who = who or disputed.attributed_to or "Another source"
        clauses.append({"text": f"; {who} disputed the account", "priority": 80,
                        "required": False, "slot": "disputed"})

    # A second supporting fact, so a thin story still says something.
    extras = [f for f in pool if f is not what][:1]
    for extra in extras:
        _, body = split_attribution(extra.text)
        core = _core_statement(body)
        if core and not set(tokenize(core)) <= headline_tokens:
            clauses.append({"text": f"; {_soft_lower(core)}", "priority": 30,
                           "required": False, "slot": "detail"})

    return clauses


def _needs_on(date_text: str) -> bool:
    lowered = date_text.lower()
    return not lowered.startswith(("today", "yesterday", "tomorrow", "this", "next", "last"))


def _number_label(context: str, number: str, max_words: int = 8) -> str:
    """Turn a bare figure into a short phrase using its own surrounding words.

    "40,000" tells a reader nothing; "40,000 evacuated as Cyclone Verath" does.
    The phrase is built only from words adjacent to the figure in the source,
    never crosses a sentence boundary, and is dropped rather than shipped broken.
    """
    if not context:
        return number
    idx = context.lower().find(number.lower())
    if idx < 0:
        return number

    before, after = context[:idx], context[idx + len(number):]
    # Stay inside the sentence the figure is in.
    if "." in before:
        before = before[before.rindex(".") + 1:]
    sentence_end = re.search(r"[.!?;]", after)
    if sentence_end:
        after = after[: sentence_end.start()]

    lead = before.strip().split()[-2:]
    # If the word touching the figure is a function word, the link between the
    # lead and the figure is broken and the whole lead goes ("in front of 40" ->
    # "40", never "front 40").
    while lead and lead[-1].lower().strip(".,;:") in _EDGE_JUNK:
        lead = []
    while lead and lead[0].lower().strip(".,;:") in _EDGE_JUNK:
        lead.pop(0)
    tail_words = after.strip(" ,.;:").split()
    take = min(3, len(tail_words))
    # Do not stop halfway through a name: "40,000 evacuated as Cyclone" should
    # either include "Verath" or drop the fragment entirely.
    while take < len(tail_words) and tail_words[take][:1].isupper():
        take += 1
    tail = _trim_edges(tail_words[:take])

    phrase = " ".join([*lead, number, *tail]).strip(" ,.;:")
    if not phrase or count_words(phrase) > max_words:
        return number
    return phrase


def is_place(entity: str) -> bool:
    return _is_place(entity)


def entity_matches(a: str, b: str) -> bool:
    return entities_match(a, b)
