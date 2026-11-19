"""Whose words go on the card, when Briefly has no words of its own.

A feed item is a headline and a sentence. From that, a program without a
language model cannot write an original summary: every "summary" it produces is
the publisher's sentence with the clauses shuffled, which is copying with extra
steps, reads badly, and — the part that matters — presents somebody else's
reporting as Briefly's own account of events.

So this module does the honest thing instead. It picks **one outlet** from the
cluster and puts that outlet's own headline and opening line on the card,
unaltered and credited by name. Nothing is reworded, so nothing can be
distorted; the reader sees exactly whose account they are reading, and the
source list beneath shows everyone else who reported it.

The rules that make this safe to automate:

* **Verbatim or nothing.** The excerpt is a contiguous span of the outlet's own
  feed text. It may be shortened — at a sentence end, or at a clause boundary
  with an ellipsis — but never edited. Quality control re-checks this against
  the source before anything is published.
* **Thirty words, counted in code.** Same budget as every other card.
* **The plainest account wins.** Among the outlets in a cluster, the one whose
  headline and opening line are the most complete, the least loaded, and the
  closest to what the others reported is chosen. If every available wording is
  sensational or editorialising, the story is held rather than shown.
* **No description: the headline alone, said plainly.** Some publishers —
  most law reporters among them — put only a headline in their feed. Such a
  story may still be shown, but as exactly that: the outlet's own headline,
  credited, with no summary under it and a line on the card saying the feed
  carried no summary. Nothing is written to fill the gap. A description is
  always preferred when any outlet in the cluster supplied one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.llm.schema import SourceDocument
from app.text.normalize import clean_text, extract_numbers, tokenize
from app.text.style_guard import StyleReport, check
from app.text.wordcount import count_words, normalise_whitespace, split_sentences

ELLIPSIS = "…"

# Feed furniture that is not part of the report.
_BOILERPLATE = re.compile(
    r"\b(?:read\s+more|click\s+here|continue\s+reading|read\s+the\s+full|full\s+story|"
    r"also\s+read|subscribe|sign\s+up|follow\s+us|download\s+the\s+app|"
    r"appeared\s+first\s+on|for\s+more\s+(?:news|updates|details)|stay\s+tuned|"
    r"watch\s+(?:the\s+)?video|see\s+pics|view\s+(?:photos|gallery)|"
    r"file\s+photo|representational\s+image|image\s+(?:credit|source)|photo\s*:|"
    r"all\s+rights\s+reserved|terms\s+of\s+use|whatsapp\s+channel)\b",
    re.IGNORECASE,
)

# "NEW DELHI:", "Mumbai, Nov 12 (PTI):", "New Delhi [India], November 12 (ANI):"
_DATELINE = re.compile(
    r"^(?:[A-Z][A-Za-z.'’\- ]{1,28}"
    r"(?:\s*\[[A-Za-z ]{2,20}\])?"
    r"(?:,\s*[A-Z][a-z]{2,8}\.?\s+\d{1,2})?"
    r"(?:\s*\((?:[A-Z][A-Za-z]{1,9})\))?"
    r"\s*[:—–-]\s+)(?=[A-Z0-9“\"'])"
)

_TERMINAL = re.compile(r"[.!?][\"”’')\]]*$")
_SOURCE_CUT = re.compile(r"(?:\.{3}|…|\[\s*(?:…|\.{3})\s*\])\s*$")

# Words a sentence should not be left hanging on when it is cut short.
_DANGLING = {
    "a", "an", "the", "of", "to", "in", "on", "at", "for", "and", "or", "but",
    "with", "by", "from", "as", "that", "which", "who", "whose", "is", "are",
    "was", "were", "be", "been", "has", "have", "had", "will", "would", "its",
    "his", "her", "their", "after", "before", "amid", "over", "into", "than",
    "while", "when", "because", "also", "not", "no", "said", "says",
}

# Where a sentence can be cut so that what is left still stands up.
_BOUNDARY_NEXT = {
    "after", "amid", "as", "while", "because", "although", "though", "but",
    "which", "who", "when", "where", "following", "citing", "despite",
    "according", "with", "saying", "adding",
}

MIN_LEDE_WORDS = 7
MIN_WORDS_AFTER_CUT = 10

# Prefer a primary source's own words when it is in the cluster.
_KIND_BONUS = {"official": 0.35, "wire": 0.20}


@dataclass
class Excerpt:
    text: str = ""
    word_count: int = 0
    truncated: bool = False          # shortened here to fit the budget
    source_truncated: bool = False   # the feed itself cut the sentence off

    @property
    def body(self) -> str:
        """The quoted span without the ellipsis that marks a cut."""
        return self.text.rstrip(ELLIPSIS).rstrip()


@dataclass
class CardWording:
    headline: str = ""
    summary: str = ""
    word_count: int = 0
    source_index: int | None = None
    source_slug: str = ""
    source_name: str = ""
    truncated: bool = False
    score: float = 0.0
    notes: list[str] = field(default_factory=list)
    style: StyleReport = field(default_factory=StyleReport)
    considered: int = 0
    # True when no outlet's feed carried a usable description, so the card is
    # one outlet's own headline, credited, with no summary beneath it.
    headline_only: bool = False

    @property
    def ok(self) -> bool:
        has_words = bool(self.summary) or self.headline_only
        return bool(has_words and self.source_name and self.style.ok)

    def as_dict(self) -> dict:
        return {
            "kind": "excerpt",
            "text": self.summary,
            "word_count": self.word_count,
            "source": self.source_name,
            "headline_only": self.headline_only,
            "truncated": self.truncated,
            "considered": self.considered,
            "ok": self.ok,
            "style": self.style.as_dict(),
            "notes": self.notes,
        }


# --- the excerpt -------------------------------------------------------------


def report_text(summary: str) -> str:
    """A feed description with markup, dateline and trailing furniture removed.

    Everything removed comes off the *ends*; the middle is never touched, so
    any span of the result is still a span of what the outlet wrote.
    """
    text = normalise_whitespace(clean_text(summary))
    text = _DATELINE.sub("", text, count=1)
    sentences = split_sentences(text)
    while sentences and _BOILERPLATE.search(sentences[-1]):
        sentences.pop()
    while sentences and _BOILERPLATE.search(sentences[0]):
        sentences.pop(0)
    return " ".join(sentences).strip()


def _is_clause_boundary(words: list[str], i: int) -> bool:
    """Can the sentence be cut before ``words[i]`` and still stand up?

    A comma is only a boundary when a clause follows it. In "by Pakistan, Saudi
    Arabia and Turkey" the commas separate a list, and cutting there produces
    "the first joint visit to Tehran by Pakistan…" — true of one country and
    said of one country, when the outlet said it of three.
    """
    last = words[i - 1]
    nxt_raw = words[i].strip("\"'“”‘’(") if i < len(words) else ""
    nxt = nxt_raw.lower()
    if nxt in _BOUNDARY_NEXT:
        return True
    if last.endswith((";", ":", "—", "–")):
        return True
    if last.endswith(","):
        return bool(nxt_raw) and nxt_raw[:1].islower() and nxt not in {"and", "or"}
    return False


def _cut_to_budget(sentence: str, limit: int) -> str | None:
    """Shorten one over-long sentence at the latest boundary that fits.

    Returns ``None`` when no cut leaves something worth quoting.
    """
    words = sentence.split()
    # Longest prefix inside the budget, by the same counter the card uses.
    end = len(words)
    while end > 0 and count_words(" ".join(words[:end])) > limit:
        end -= 1
    if end < MIN_WORDS_AFTER_CUT:
        return None

    cut = None
    for i in range(end, MIN_WORDS_AFTER_CUT - 1, -1):
        if _is_clause_boundary(words, i):
            cut = i
            break
    kept = words[: cut or end]
    while kept and kept[-1].lower().strip(",;:—–\"'“”‘’()") in _DANGLING:
        kept.pop()
    if len(kept) < MIN_WORDS_AFTER_CUT:
        return None
    return " ".join(kept).rstrip(",;:—– ") + ELLIPSIS


def make_excerpt(summary: str, limit: int = 30) -> Excerpt:
    """The opening of a feed description, verbatim, within ``limit`` words."""
    text = report_text(summary)
    if not text:
        return Excerpt()

    source_cut = bool(_SOURCE_CUT.search(text))
    text = _SOURCE_CUT.sub("", text).rstrip()
    sentences = split_sentences(text)
    if not sentences:
        return Excerpt()

    complete = [bool(_TERMINAL.search(s)) for s in sentences]
    # The feed cut its own last sentence short: it is a fragment, whatever
    # punctuation it happens to end on.
    if source_cut:
        complete[-1] = False

    first = sentences[0]
    if count_words(first) > limit:
        cut = _cut_to_budget(first, limit)
        if cut is None:
            return Excerpt()
        return Excerpt(text=cut, word_count=count_words(cut), truncated=True,
                       source_truncated=source_cut and len(sentences) == 1)

    if not complete[0]:
        # One unfinished sentence: the feed stopped mid-way. Quote all of it
        # that is there, minus a word left dangling at the break, and mark
        # plainly that it stops.
        words = first.split()
        while words and words[-1].lower().strip(",;:—–\"'“”‘’()") in _DANGLING:
            words.pop()
        fragment = " ".join(words).rstrip(",;:—– ")
        if count_words(fragment) < MIN_LEDE_WORDS:
            return Excerpt()
        fragment += ELLIPSIS
        return Excerpt(text=fragment, word_count=count_words(fragment),
                       truncated=True, source_truncated=True)

    kept = [first]
    for sentence, whole in zip(sentences[1:], complete[1:], strict=False):
        if not whole:
            break
        if count_words(" ".join([*kept, sentence])) > limit:
            break
        kept.append(sentence)
    text = " ".join(kept)
    return Excerpt(text=text, word_count=count_words(text))


def is_verbatim(excerpt: str, source_text: str) -> bool:
    """Is ``excerpt`` an unaltered span of ``source_text``?

    Compared after whitespace is normalised and typographic quotes are folded,
    because feeds are inconsistent about both and neither changes a word.
    """

    def fold(value: str) -> str:
        value = normalise_whitespace(clean_text(value))
        for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'")):
            value = value.replace(a, b)
        return value

    body = fold(excerpt.rstrip(ELLIPSIS).rstrip())
    return bool(body) and body in fold(source_text)


# --- choosing the outlet ------------------------------------------------------


def _restates(lede: str, headline: str) -> bool:
    """Does the opening line add nothing the headline has not already said?"""
    a, b = set(tokenize(lede)), set(tokenize(headline))
    if not a or not b:
        return False
    return len(a - b) <= 1 and len(a & b) / len(a) >= 0.85


def _centrality(index: int, token_sets: list[set[str]]) -> float:
    """How much of what this outlet says is echoed by the others."""
    mine = token_sets[index]
    others = [t for i, t in enumerate(token_sets) if i != index and t]
    if not mine or not others:
        return 0.5
    return sum(len(mine & other) / len(mine) for other in others) / len(others)


def choose_wording(
    documents: list[SourceDocument],
    *,
    limit: int = 30,
    clean_headline=None,
    allow_headline_only: bool = False,
) -> CardWording:
    """Pick the outlet whose own headline and opening line go on the card.

    With ``allow_headline_only``, a cluster in which no outlet supplied a
    quotable description gets one outlet's own headline, credited, and no
    summary — rather than being held.
    """
    if clean_headline is None:
        from app.llm.rule_based import clean_headline as _clean

        def clean_headline(doc: SourceDocument) -> str:
            return _clean(doc.headline, publisher=doc.source_name)

    token_sets = [set(tokenize(f"{d.headline} {d.summary}")) for d in documents]
    best: CardWording | None = None
    fallback_notes: list[str] = []
    considered = 0

    for position, doc in enumerate(documents):
        headline = clean_headline(doc)
        if not headline:
            continue
        excerpt = make_excerpt(doc.summary, limit)
        if not excerpt.text:
            fallback_notes.append(f"{doc.source_name}: no usable description")
            continue
        if count_words(excerpt.body) < MIN_LEDE_WORDS:
            fallback_notes.append(f"{doc.source_name}: description too short")
            continue
        if _restates(excerpt.body, headline):
            fallback_notes.append(f"{doc.source_name}: description repeats the headline")
            continue
        considered += 1

        # Attribution is supplied by the card itself ("Wording: The Hindu"), so
        # an allegation in the outlet's words is an attributed allegation.
        style = StyleReport()
        for text in (headline, excerpt.text):
            style.findings.extend(
                check(text, require_attribution_for_allegations=False).findings
            )
        blockers = sum(1 for f in style.findings if f.severity == "blocker")
        warnings = len(style.findings) - blockers

        quality = 0.0
        quality += 0.0 if excerpt.truncated else 1.0
        quality -= 0.6 if excerpt.source_truncated else 0.0
        quality += 0.5 if 12 <= excerpt.word_count <= limit else 0.0
        quality += 0.2 if extract_numbers(excerpt.text) else 0.0
        quality -= 0.5 if headline.endswith("?") else 0.0

        score = (
            2.0 * _centrality(position, token_sets)
            + quality
            + _KIND_BONUS.get(doc.source_kind, 0.0)
            - 3.0 * blockers
            - 0.3 * warnings
        )
        if best is None or score > best.score:
            best = CardWording(
                headline=headline,
                summary=excerpt.text,
                word_count=excerpt.word_count,
                source_index=doc.index,
                source_slug=doc.source_slug,
                source_name=doc.source_name,
                truncated=excerpt.truncated,
                score=round(score, 4),
                style=style,
            )

    if best is None and allow_headline_only:
        headline_card = _headline_only(documents, token_sets, clean_headline)
        if headline_card is not None:
            headline_card.notes = [
                "no outlet supplied a description; the card is the credited headline only",
                *fallback_notes[:5],
            ]
            return headline_card

    if best is None:
        # Nothing quotable. Keep the plainest headline so the held story can
        # still be identified in the review queue, and say why it was held.
        headline = next((clean_headline(d) for d in documents if clean_headline(d)), "")
        return CardWording(
            headline=headline,
            notes=["no outlet supplied a description that could be quoted",
                   *fallback_notes[:6]],
            considered=0,
        )

    best.considered = considered
    best.notes = fallback_notes[:6]
    if best.truncated:
        best.notes.append("excerpt shortened to fit the word budget")
    return best


def _headline_only(documents, token_sets, clean_headline) -> CardWording | None:
    """The plainest headline in the cluster, credited to the outlet that ran it.

    Chosen the same way as an excerpt — closest to what the others reported,
    least loaded, primary sources first — but there is no summary to quote.
    """
    best: CardWording | None = None
    for position, doc in enumerate(documents):
        headline = clean_headline(doc)
        if not headline or not doc.source_name:
            continue
        style = StyleReport()
        style.findings.extend(
            check(headline, require_attribution_for_allegations=False).findings
        )
        blockers = sum(1 for f in style.findings if f.severity == "blocker")
        warnings = len(style.findings) - blockers
        score = (
            2.0 * _centrality(position, token_sets)
            + _KIND_BONUS.get(doc.source_kind, 0.0)
            - (0.5 if headline.endswith("?") else 0.0)
            - 3.0 * blockers
            - 0.3 * warnings
        )
        if best is None or score > best.score:
            best = CardWording(
                headline=headline,
                summary="",
                word_count=0,
                source_index=doc.index,
                source_slug=doc.source_slug,
                source_name=doc.source_name,
                score=round(score, 4),
                style=style,
                headline_only=True,
                considered=1,
            )
    return best
