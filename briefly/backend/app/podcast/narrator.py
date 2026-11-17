"""Deterministic narration from structured facts.

This is the offline narrator: it works with no credentials and is what the tests
pin. When a hosted model is configured it writes the prose instead, but the
paragraph *plan* below is what it is asked for, and every gate in
``app/pipeline/qc.py`` applies to either.

Two things it will not do:

* read a publisher's sentences back — narration is assembled from fact rows,
  and quality control measures n-gram overlap against every source;
* fill time. If the sources do not support ten minutes of material, the script
  is shorter and says what is not known.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from app.podcast.brief import FactRef, StoryBrief
from app.text.normalize import tokenize
from app.text.style_guard import neutralise
from app.text.wordcount import count_words, normalise_whitespace

WORDS_PER_MINUTE = 150

# Words that belong to Briefly's own narration templates rather than to any
# publisher. Quality control needs this list: without it, the show's framing
# ("here is what is confirmed", "that's the Deep Dive") looks like unsourced
# assertion, and the grounding check fires on Briefly's own voice.
FRAMING_VOCABULARY: frozenset[str] = frozenset(
    """
    good morning afternoon evening this is briefly daily deep dive for story
    stories today todays here are the most important across everything you hear
    assembled from sources named alongside it where reporting contested we say so
    rather than picking a side first what happened confirmed and by whom now how
    different outlets reported led with where accounts diverge on central facts
    checked do not contradict each other why matters going only what states
    figure to hold onto figures are reported independent among them official
    statement record disputed that account treat as single until other confirm
    part of not settled describes likely there set out without wider consequences
    neither will happens next those expectations settled outcomes does say comes
    when updated thats your briefing every in this episode cards app full list
    links original all shorter usual because available still thin would stop fill
    time quoted listed card so can check any yourself an outlet wire service
    international regional national source nothing has been independently yet
    follows attributed outlet reported framings differed a little framed slightly
    differently wording varied between was reported in on introduction outro
    """.split()
)


def estimate_seconds(text: str, wpm: int = WORDS_PER_MINUTE) -> int:
    return int(round(count_words(text) / max(wpm, 1) * 60))


def _pick(options: list[str], seed: str) -> str:
    """Stable variation: the same story always gets the same phrasing."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return options[digest[0] % len(options)]


def _sentence(text: str) -> str:
    text = normalise_whitespace(neutralise(text))
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    if text[-1] not in ".?":
        text += "."
    return text


# Only these openers are safe to down-case when a clause is spliced mid-sentence.
# Anything else keeps its capitalisation, so "RBI" never becomes "rBI".
_SAFE_OPENERS = {
    "the", "a", "an", "this", "that", "these", "those", "it", "its", "he",
    "she", "they", "there", "his", "her", "their", "officials", "police",
    "authorities", "government", "opposition", "several", "many", "most",
    "some", "two", "three", "four", "five", "more", "no", "after", "amid",
    "following", "because", "since", "while", "economists", "analysts",
    "residents", "workers", "students", "farmers", "shares", "prices",
}


def _lower_first(text: str) -> str:
    text = normalise_whitespace(text).rstrip(".")
    if not text:
        return text
    first = text.split(" ", 1)[0]
    stripped = first.strip("\"'“”‘’()")
    if stripped.lower() in _SAFE_OPENERS and stripped[1:].islower():
        return text[0].lower() + text[1:]
    return text


def _list_sources(names: list[str], limit: int = 4) -> str:
    names = [n for n in names if n][:limit]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _restates(text: str, reference: str, threshold: float = 0.8) -> bool:
    """Would saying this again just repeat what the listener heard a moment ago?"""
    a, b = set(tokenize(text)), set(tokenize(reference))
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= threshold


def _sourcing_sentence(brief: StoryBrief) -> str:
    n = brief.independent_source_count or brief.source_count
    names = _list_sources(brief.source_names)
    if n <= 1:
        return _sentence(
            f"So far this is a single-source report, from {names or 'one publication'}"
        )
    lead = _pick(
        [
            f"{n} independent outlets carried this, including {names}",
            f"It was reported by {n} independent outlets, among them {names}",
            f"{names} were among the {n} independent outlets reporting it",
        ],
        brief.story_id + "sourcing",
    )
    if brief.has_official_source:
        lead += ", and an official statement is on the record"
    return _sentence(lead)


def _numbers_sentence(brief: StoryBrief, limit: int = 3) -> str:
    numbers: list[str] = []
    for fact in brief.numbers[:limit]:
        text = fact.text.strip()
        if text and text not in numbers:
            numbers.append(text)
    if not numbers:
        return ""
    if len(numbers) == 1:
        return _sentence(f"The figure to hold on to is {numbers[0]}")
    return _sentence("The figures reported are " + _list_sources(numbers, limit=limit))


def _attribution_sentences(facts: list[FactRef], limit: int = 3) -> list[str]:
    out: list[str] = []
    for fact in facts[:limit]:
        who = fact.attributed_to
        body = _lower_first(fact.text)
        if not body:
            continue
        if who:
            frame = _pick(
                [f"According to {who}, {body}",
                 f"{who} said {body}",
                 f"{who} stated that {body}"],
                fact.text,
            )
        else:
            frame = body
        out.append(_sentence(frame))
    return out


def _dispute_sentences(brief: StoryBrief, limit: int = 2) -> list[str]:
    out: list[str] = []
    for fact in brief.disputed[:limit]:
        who = fact.attributed_to or "another source"
        out.append(_sentence(f"{who} disputed that account: {_lower_first(fact.text)}"))
    return out


def _uncertainty_sentence(brief: StoryBrief) -> str:
    if brief.uncertain:
        fact = brief.uncertain[0]
        return _sentence(
            f"One part of this is not settled. {fact.attributed_to or 'The reporting'} "
            f"describes it only as likely: {_lower_first(fact.text)}"
        )
    if brief.independent_source_count <= 1:
        return _sentence("Treat it as a single account until other outlets confirm it")
    return ""


def compose_daily_segment(brief: StoryBrief, target_words: int = 130) -> str:
    """One story as it appears inside Briefly Daily.

    Detail is added in order of value while there is room in ``target_words``.
    When the sources do not support the target, the segment simply ends — the
    episode gets more stories rather than more padding.
    """
    parts: list[str] = []
    parts.append(_sentence(brief.headline))

    detail = [
        f
        for f in (brief.confirmed or brief.attributed)
        if f.slot in {"what", "why"} and not _restates(f.text, brief.headline)
    ]
    if detail:
        parts.extend(_attribution_sentences(detail, limit=2))
    elif brief.summary and not _restates(brief.summary, brief.headline):
        parts.append(_sentence(brief.summary))

    numbers = _numbers_sentence(brief)
    if numbers:
        parts.append(numbers)

    parts.append(_sourcing_sentence(brief))
    parts.extend(_dispute_sentences(brief, limit=1))

    # Optional depth, cheapest-first, while the budget allows it.
    def room() -> int:
        return target_words - count_words(" ".join(parts))

    if room() > 25:
        where = brief.by_slot("where")
        when = brief.by_slot("when")
        context = []
        if where:
            context.append(f"in {where[0].text}")
        if when:
            context.append(f"on {when[0].text}")
        if context:
            parts.append(_sentence("This was reported " + " ".join(context)))

    if room() > 35:
        extra = [f for f in brief.attributed if f.slot in {"what", "why"}][2:5]
        parts.extend(_attribution_sentences(extra, limit=2))

    if room() > 45 and len(brief.sources) >= 2:
        variants = [s for s in brief.sources[:3] if s.headline]
        if variants:
            lead = _pick(
                ["Framings differed a little", "The outlets framed it slightly differently",
                 "The wording varied between outlets"],
                brief.story_id + "frames",
            )
            joined = "; ".join(
                f"{s.name} led with {_lower_first(s.headline)}" for s in variants[:2]
            )
            parts.append(_sentence(f"{lead}: {joined}"))

    uncertainty = _uncertainty_sentence(brief)
    if uncertainty:
        parts.append(uncertainty)

    return _fit(parts, target_words)


def compose_deep_dive(brief: StoryBrief, target_words: int = 1600) -> str:
    """A single story, explained. Sections flow as speech, not headings."""
    sections: list[str] = []

    # 1. What happened
    opening = [
        _sentence(f"First, what happened. {brief.headline}"),
    ]
    if brief.dek and not _restates(brief.dek, brief.headline):
        opening.append(_sentence(brief.dek))
    elif brief.summary and not _restates(brief.summary, brief.headline):
        opening.append(_sentence(brief.summary))
    where = brief.by_slot("where")
    when = brief.by_slot("when")
    if where:
        opening.append(_sentence(f"This is happening in {where[0].text}"))
    if when:
        opening.append(_sentence(f"The reporting places it on {when[0].text}"))
    sections.append(" ".join(p for p in opening if p))

    # 2. What is confirmed
    confirmed = [f for f in brief.confirmed if not _restates(f.text, brief.headline)]
    if confirmed:
        block = [_sentence("Here is what is confirmed")]
        block.extend(_attribution_sentences(confirmed, limit=4))
        block.append(_sourcing_sentence(brief))
        sections.append(" ".join(block))
    else:
        sections.append(
            _sentence(
                "Nothing here has been independently confirmed yet. Everything that follows "
                "is attributed to the outlet that reported it"
            )
        )

    # 3. What different sources report — scales with how well covered the story is
    if brief.sources:
        block = [_sentence("Now, how the different outlets reported it")]
        for source in brief.sources[:8]:
            kind = {
                "official": "an official source",
                "wire": "a wire service",
                "international": "an international outlet",
                "regional": "a regional outlet",
                "national": "a national outlet",
            }.get(source.kind, "an outlet")
            block.append(
                _sentence(
                    f"{source.name}, {kind}, led with: {_lower_first(source.headline)}"
                )
            )
        sections.append(" ".join(block))

    # 4. Where sources disagree
    disputes = _dispute_sentences(brief, limit=4)
    if disputes:
        sections.append(
            " ".join([_sentence("Where the accounts diverge"), *disputes])
        )
    else:
        sections.append(
            _sentence(
                "On the central facts, the outlets we checked do not contradict each other"
            )
        )

    # 5. Why it matters — strictly from what the facts say
    why = brief.by_slot("why")
    numbers = _numbers_sentence(brief, limit=4)
    block = [_sentence("Why this matters, going only by what the reporting states")]
    if why:
        block.extend(_attribution_sentences(why, limit=3))
    if numbers:
        block.append(numbers)
    if len(block) == 1:
        block.append(
            _sentence(
                "The sources set out what happened without setting out its wider consequences, "
                "so neither will we"
            )
        )
    sections.append(" ".join(block))

    # 6. What happens next
    forward = [f for f in brief.facts if f.kind == "uncertain"] + brief.by_slot("when")[1:]
    block = [_sentence("And what happens next")]
    if forward:
        block.extend(_attribution_sentences(forward[:2], limit=2))
        block.append(
            _sentence("Those are expectations reported by the sources, not settled outcomes")
        )
    else:
        block.append(
            _sentence(
                "The reporting does not say what comes next. When it does, this story will "
                "be updated"
            )
        )
    sections.append(" ".join(block))

    return _fit(sections, target_words, joiner=" ")


def _fit(parts: list[str], target_words: int, joiner: str = " ") -> str:
    """Assemble, then trim whole sentences if we overshoot badly.

    Narration is never padded to reach a target — a short honest script beats a
    long one with filler.
    """
    text = joiner.join(p for p in parts if p).strip()
    text = re.sub(r"\s+", " ", text)
    ceiling = int(target_words * 1.35)
    if count_words(text) <= ceiling:
        return text
    kept: list[str] = []
    total = 0
    for sentence in re.split(r"(?<=[.?])\s+", text):
        words = count_words(sentence)
        if total + words > ceiling and kept:
            break
        kept.append(sentence)
        total += words
    return " ".join(kept)


def compose_narration(story_brief: dict | StoryBrief, target_words: int, mode: str = "daily") -> str:
    brief = (
        story_brief
        if isinstance(story_brief, StoryBrief)
        else StoryBrief.from_dict(story_brief)
    )
    if mode == "deep_dive":
        return compose_deep_dive(brief, target_words=target_words)
    return compose_daily_segment(brief, target_words=target_words)


def format_edition_date(value: datetime) -> str:
    return value.strftime("%A, %-d %B %Y") if hasattr(value, "strftime") else str(value)
