"""Building the ≤30-word card summary from extracted facts.

The order of operations is deliberate and is what the "30-word rule" section of
the product spec asks for:

1. facts are already extracted (``app/pipeline/facts.py``);
2. facts become *ranked clauses*, each with a priority and a required flag;
3. clauses that repeat information already selected are dropped;
4. :class:`~app.text.wordcount.WordBudget` decides what fits — in code;
5. the result is checked by the style guard and re-validated against the cap.

Nothing here asks a model to be brief. Brevity is arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import get_settings
from app.llm.schema import ExtractionResult, SourceDocument
from app.text.normalize import tokenize
from app.text.style_guard import StyleReport, check, neutralise
from app.text.wordcount import Clause, WordBudget, count_words, normalise_whitespace

# Clause slots that must never be dropped for being redundant.
_ALWAYS_KEEP = {"what", "disputed"}
# How much a clause may echo what has already been said before it is dropped.
# Supporting clauses are held to a stricter bar: their whole job is to add
# something new, so a half-repeat is not worth the words it costs.
_OVERLAP_LIMIT = {"detail": 0.5, "why": 0.6, "number": 0.6}
_DEFAULT_OVERLAP_LIMIT = 0.8


@dataclass
class SummaryResult:
    text: str
    word_count: int
    limit: int
    ok: bool
    clauses_used: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    style: StyleReport = field(default_factory=StyleReport)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "word_count": self.word_count,
            "limit": self.limit,
            "ok": self.ok,
            "clauses_used": self.clauses_used,
            "dropped": self.dropped,
            "style": self.style.as_dict(),
            "notes": self.notes,
        }


def _dedupe_clauses(clauses: list[dict]) -> list[dict]:
    """Drop clauses whose content is already carried by a stronger clause."""
    ordered = sorted(clauses, key=lambda c: -c.get("priority", 50))
    kept: list[dict] = []
    seen_tokens: set[str] = set()
    for clause in ordered:
        toks = set(tokenize(clause["text"]))
        if not toks:
            continue
        slot = clause.get("slot", "other")
        if slot not in _ALWAYS_KEEP and toks and toks <= seen_tokens:
            continue
        if slot not in _ALWAYS_KEEP and toks:
            overlap = len(toks & seen_tokens) / len(toks)
            if overlap >= _OVERLAP_LIMIT.get(slot, _DEFAULT_OVERLAP_LIMIT):
                continue
        seen_tokens |= toks
        kept.append(clause)
    # Restore the caller's ordering so the sentence still reads naturally.
    original = {id(c): i for i, c in enumerate(clauses)}
    kept.sort(key=lambda c: original[id(c)])
    return kept


def _glue(clauses: list[dict]) -> list[Clause]:
    """Attach the small connective words that make a run of clauses a sentence."""
    out: list[Clause] = []
    for i, clause in enumerate(clauses):
        text = normalise_whitespace(clause["text"])
        slot = clause.get("slot", "other")
        prev_slot = clauses[i - 1].get("slot") if i > 0 else None
        needs_comma = (
            i > 0
            and slot in {"why", "number", "when"}
            and not text.startswith((",", ";"))
            # "in Delhi on Friday" reads better than "in Delhi, on Friday".
            and not (slot == "when" and prev_slot == "where")
        )
        if needs_comma:
            text = f", {text}"
        out.append(
            Clause(
                text=text,
                priority=int(clause.get("priority", 50)),
                required=bool(clause.get("required", False)),
            )
        )
    return out


def build_summary(
    extraction: ExtractionResult,
    documents: list[SourceDocument] | None = None,
    *,
    limit: int | None = None,
) -> SummaryResult:
    settings = get_settings()
    limit = limit or settings.summary_max_words
    budget = WordBudget(limit)

    clauses = _dedupe_clauses([dict(c) for c in extraction.summary_clauses])
    if not clauses:
        fallback = normalise_whitespace(extraction.headline or "")
        enforced = budget.enforce(fallback)
        return SummaryResult(
            text=enforced.text,
            word_count=enforced.word_count,
            limit=limit,
            ok=bool(enforced.text) and enforced.ok,
            notes=["no clauses available; fell back to the neutral headline"],
            style=check(enforced.text),
        )

    assembled = budget.assemble(_glue(clauses))

    # A three-word card is technically within budget and useless. If the chosen
    # clauses left most of the budget unspent, add back the strongest clause the
    # dedupe pass removed rather than shipping a stub.
    if assembled.word_count < 10:
        removed = [
            c
            for c in extraction.summary_clauses
            if c["text"] not in {k["text"] for k in clauses}
        ]
        if removed:
            clauses = clauses + removed[: max(1, 3 - len(clauses))]
            assembled = budget.assemble(_glue(clauses))
        elif extraction.headline and assembled.word_count < 8:
            clauses = clauses + [
                {"text": extraction.headline, "priority": 5, "required": False,
                 "slot": "headline_fallback"}
            ]
            assembled = budget.assemble(_glue(clauses))

    text = neutralise(assembled.text)

    # Neutralising can change the word count; re-check rather than assume.
    revalidated = budget.validate(text)
    notes: list[str] = []
    if not revalidated.ok:
        trimmed = budget.enforce(text)
        text = trimmed.text
        notes.append("re-trimmed after neutralisation")

    style = check(text)
    if not style.ok:
        # Try once with the offending wording softened, then report honestly.
        softened = neutralise(text)
        if softened != text:
            text = budget.enforce(softened).text
            style = check(text)
        if not style.ok:
            notes.append("style guard flagged the summary; story will not auto-publish")

    final = count_words(text)
    return SummaryResult(
        text=text,
        word_count=final,
        limit=limit,
        ok=final <= limit and final > 0 and style.ok,
        clauses_used=[c["text"] for c in clauses],
        dropped=assembled.dropped,
        style=style,
        notes=notes + ([assembled.reason] if assembled.reason else []),
    )
