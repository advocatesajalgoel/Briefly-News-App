"""The 30-word rule, enforced in code.

Nothing here asks a model to "please keep it short". A summary is *built* from
ranked clauses and this module decides, deterministically, which clauses fit.
The database additionally refuses to store a summary over the cap
(``ck_stories_summary_max_30_words``), so a prompt regression cannot leak
through.

Word counting rules (documented because "how many words is this" is otherwise
ambiguous):

* A word is a maximal run of letters/digits that may contain internal
  apostrophes, hyphens or periods (``don't``, ``cease-fire``, ``U.S.``,
  ``26.5``). Hyphenated compounds count as ONE word — this is the generous
  reading, so it is checked against the strict reading too and the larger of
  the two is what the cap applies to.
* Standalone punctuation, quotes, dashes and symbols are not words.
* ``₹1,200 crore`` counts as two words (``₹1,200`` and ``crore``).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Generous tokenizer: internal ' - . are kept inside a token.
_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ɏऀ-ॿ]+(?:['’.\-][0-9A-Za-zÀ-ɏऀ-ॿ]+)*")
# Strict tokenizer: a hyphen splits.
_STRICT_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ɏऀ-ॿ]+(?:['’.][0-9A-Za-zÀ-ɏऀ-ॿ]+)*")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"'])")


def normalise_whitespace(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def words(text: str) -> list[str]:
    """Tokens under the generous (hyphen-joining) reading."""
    return _WORD_RE.findall(normalise_whitespace(text))


def strict_words(text: str) -> list[str]:
    """Tokens under the strict (hyphen-splitting) reading."""
    return _STRICT_WORD_RE.findall(normalise_whitespace(text))


def count_words(text: str, *, strict: bool = True) -> int:
    """Number of words in ``text``.

    ``strict=True`` (the default, and what the cap uses) takes the larger of the
    two readings, so ``cease-fire`` costs two words. Being pessimistic here means
    a card can never be accused of exceeding 30 words on a technicality.
    """
    if not text:
        return 0
    generous = len(words(text))
    if not strict:
        return generous
    return max(generous, len(strict_words(text)))


def split_sentences(text: str) -> list[str]:
    text = normalise_whitespace(text)
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


@dataclass(frozen=True)
class Clause:
    """A candidate piece of a summary.

    ``priority`` decides what survives when the budget is tight (higher = keep
    first). ``required`` clauses are never dropped; if the required clauses
    alone overflow, the result is marked invalid and the caller must re-plan
    rather than silently emitting a mangled sentence.
    """

    text: str
    priority: int = 50
    required: bool = False

    @property
    def word_count(self) -> int:
        return count_words(self.text)


@dataclass
class WordBudgetResult:
    text: str
    word_count: int
    limit: int
    ok: bool
    dropped: list[str] = field(default_factory=list)
    truncated: bool = False
    reason: str = ""

    @property
    def within_budget(self) -> bool:
        return self.word_count <= self.limit


class WordBudget:
    """Reusable word-count enforcement.

    Two entry points:

    * :meth:`assemble` — build text from ranked clauses, dropping the least
      important ones until it fits. This is how summaries are produced.
    * :meth:`enforce` — last line of defence for text produced elsewhere
      (an LLM, a human edit). Trims whole sentences first, then whole words.
    """

    def __init__(self, limit: int = 30, *, min_words: int = 6) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self.limit = limit
        self.min_words = min(min_words, limit)

    # -- building ---------------------------------------------------------
    def assemble(self, clauses: list[Clause], *, joiner: str = " ") -> WordBudgetResult:
        required = [c for c in clauses if c.required]
        optional = sorted(
            (c for c in clauses if not c.required),
            key=lambda c: (-c.priority, c.word_count),
        )

        kept: list[Clause] = list(required)
        used = sum(c.word_count for c in kept)
        dropped: list[str] = []

        if used > self.limit:
            # Required content alone overflows — report honestly instead of
            # producing a chopped sentence.
            text = _join(kept, joiner)
            enforced = self.enforce(text)
            enforced.ok = False
            enforced.reason = "required clauses exceed the word budget"
            return enforced

        for clause in optional:
            if used + clause.word_count <= self.limit:
                kept.append(clause)
                used += clause.word_count
            else:
                dropped.append(clause.text)

        # Preserve the caller's original ordering for readability.
        order = {id(c): i for i, c in enumerate(clauses)}
        kept.sort(key=lambda c: order[id(c)])

        text = _join(kept, joiner)
        count = count_words(text)
        return WordBudgetResult(
            text=text,
            word_count=count,
            limit=self.limit,
            ok=count <= self.limit and count >= min(self.min_words, count),
            dropped=dropped,
            truncated=False,
            reason="" if count <= self.limit else "assembled text still over budget",
        )

    # -- trimming ---------------------------------------------------------
    def enforce(self, text: str) -> WordBudgetResult:
        text = normalise_whitespace(text)
        count = count_words(text)
        if count <= self.limit:
            return WordBudgetResult(text=text, word_count=count, limit=self.limit, ok=True)

        # 1) Drop trailing sentences while more than one remains.
        sentences = split_sentences(text)
        dropped: list[str] = []
        while len(sentences) > 1 and count_words(" ".join(sentences)) > self.limit:
            dropped.append(sentences.pop())
        candidate = " ".join(sentences)
        if count_words(candidate) <= self.limit:
            c = count_words(candidate)
            return WordBudgetResult(
                text=candidate,
                word_count=c,
                limit=self.limit,
                ok=True,
                dropped=list(reversed(dropped)),
                truncated=True,
                reason="dropped trailing sentences",
            )

        # 2) Trim words off the end of the remaining sentence, then repair the
        #    tail so it never ends on a dangling connective or punctuation.
        toks = _tokenise_with_spacing(candidate)
        while toks and count_words(_detokenise(toks)) > self.limit:
            toks.pop()
        toks = _repair_tail(toks)
        trimmed = _detokenise(toks)
        trimmed = _finalise_sentence(trimmed)
        c = count_words(trimmed)
        return WordBudgetResult(
            text=trimmed,
            word_count=c,
            limit=self.limit,
            ok=c <= self.limit,
            dropped=list(reversed(dropped)),
            truncated=True,
            reason="hard word trim",
        )

    def validate(self, text: str) -> WordBudgetResult:
        """Check without changing anything."""
        count = count_words(text)
        return WordBudgetResult(
            text=normalise_whitespace(text),
            word_count=count,
            limit=self.limit,
            ok=count <= self.limit,
            reason="" if count <= self.limit else f"{count} words exceeds limit {self.limit}",
        )


# --- module-level conveniences --------------------------------------------

_DEFAULT_BUDGET = WordBudget(30)


def fit_to_word_budget(text: str, limit: int = 30) -> str:
    """Trim ``text`` so it fits ``limit`` words. Idempotent."""
    return WordBudget(limit).enforce(text).text


# --- helpers ---------------------------------------------------------------

_DANGLING = {
    "and", "or", "but", "the", "a", "an", "of", "to", "in", "on", "at", "for",
    "with", "by", "from", "as", "that", "which", "who", "while", "after",
    "before", "over", "under", "into", "than", "then", "its", "their", "his",
    "her", "was", "were", "is", "are", "has", "have", "had", "said", "amid",
}


def _join(clauses: list[Clause], joiner: str) -> str:
    parts = [normalise_whitespace(c.text) for c in clauses if normalise_whitespace(c.text)]
    return _finalise_sentence(joiner.join(parts))


def _tokenise_with_spacing(text: str) -> list[str]:
    return normalise_whitespace(text).split(" ")


def _detokenise(tokens: list[str]) -> str:
    return " ".join(t for t in tokens if t)


def _repair_tail(tokens: list[str]) -> list[str]:
    while tokens:
        tail = tokens[-1].strip(".,;:—-–\"'“”’()")
        if not tail or tail.lower() in _DANGLING:
            tokens.pop()
            continue
        break
    return tokens


def _finalise_sentence(text: str) -> str:
    text = normalise_whitespace(text)
    if not text:
        return text
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,;:])\s*$", "", text).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text
