"""Quality control.

Nothing auto-publishes until it clears these gates. A blocker does not delete
the item — it flags it (``ProcessingStatus.FLAGGED``) with the reasons attached,
so a person can look at it. Silence is never the failure mode.

Gates, in the order the spec asks for them:

  hallucination / unsupported claim ... grounding report + per-claim recheck
  incorrect numbers .................. every figure must appear in the sources
  incorrect names .................... every capitalised name must appear
  incorrect dates .................... every date expression must appear
  duplicate stories .................. near-duplicate headline check
  repetition ......................... repeated sentences/phrases in narration
  opinionated language ............... style guard
  unattributed claims ................ allegations must name a speaker
  excessive copying .................. n-gram overlap with any single source
  length ............................. the 30-word rule, re-verified
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import get_settings
from app.enums import QCSeverity
from app.llm.schema import FactCandidate, SourceDocument
from app.pipeline.facts import _CAP_TOKEN_RE, _normalised, _numbers_in
from app.pipeline.wording import is_verbatim
from app.text.normalize import extract_dates, tokenize
from app.text.similarity import shingle_overlap
from app.text.style_guard import check as style_check
from app.text.wordcount import count_words, split_sentences


@dataclass
class QCIssue:
    code: str
    message: str
    severity: str = QCSeverity.WARNING
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass
class QCReport:
    issues: list[QCIssue] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)

    @property
    def blockers(self) -> list[QCIssue]:
        return [i for i in self.issues if i.severity == QCSeverity.BLOCKER]

    @property
    def passed(self) -> bool:
        return not self.blockers

    def add(self, code: str, message: str, severity: str = QCSeverity.WARNING,
            detail: str = "") -> None:
        self.issues.append(QCIssue(code, message, severity, detail))

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks_run": self.checks_run,
            "issues": [i.as_dict() for i in self.issues],
        }


def _corpus(documents: list[SourceDocument]) -> str:
    return " \n ".join(f"{d.headline}. {d.summary}" for d in documents)


def check_story(
    *,
    headline: str,
    summary: str,
    facts: list[FactCandidate],
    documents: list[SourceDocument],
    grounding_rejected: int = 0,
    existing_headlines: list[str] | None = None,
    summary_word_limit: int | None = None,
    summary_kind: str = "composed",
    wording_document: SourceDocument | None = None,
) -> QCReport:
    settings = get_settings()
    limit = summary_word_limit or settings.summary_max_words
    report = QCReport()
    # An excerpt is one outlet's words, quoted and credited on the card. It is
    # held to a different standard from Briefly's own prose: it must be exact
    # rather than original.
    quoted = summary_kind == "excerpt"
    corpus = _corpus(documents)
    corpus_norm = _normalised(corpus)
    corpus_tokens = set(tokenize(corpus))
    corpus_numbers = _numbers_in(corpus)
    corpus_dates = {d.lower() for d in extract_dates(corpus, limit=100)}

    # --- length ---------------------------------------------------------
    report.checks_run.append("length")
    words = count_words(summary)
    if words == 0:
        report.add("empty_summary", "The card has no summary", QCSeverity.BLOCKER)
    elif words > limit:
        report.add(
            "summary_too_long",
            f"Summary is {words} words, over the {limit}-word cap",
            QCSeverity.BLOCKER,
            detail=str(words),
        )
    elif words < 6:
        report.add("summary_too_short", f"Summary is only {words} words", QCSeverity.WARNING)

    # --- a card that says the same thing twice ---------------------------
    report.checks_run.append("repetition")
    if _repeats_itself(summary):
        report.add(
            "summary_repeats_itself",
            "The summary repeats a phrase it has already used",
            QCSeverity.BLOCKER,
        )
    if words and _says_no_more_than(summary, headline):
        report.add(
            "summary_restates_headline",
            "The summary adds nothing to the headline above it",
            QCSeverity.BLOCKER,
        )

    # --- numbers --------------------------------------------------------
    report.checks_run.append("numbers")
    for number in _numbers_in(f"{headline} {summary}"):
        if number not in corpus_numbers:
            report.add(
                "number_not_in_sources",
                f"The figure {number} does not appear in any source",
                QCSeverity.BLOCKER,
                detail=number,
            )

    # --- names ----------------------------------------------------------
    report.checks_run.append("names")
    for name in set(_CAP_TOKEN_RE.findall(f"{headline} {summary}")):
        if name.lower() not in corpus_norm:
            report.add(
                "name_not_in_sources",
                f"'{name}' does not appear in any source",
                QCSeverity.BLOCKER,
                detail=name,
            )

    # --- dates ----------------------------------------------------------
    report.checks_run.append("dates")
    for date in extract_dates(f"{headline} {summary}"):
        if date.lower() not in corpus_dates and date.lower() not in corpus_norm:
            report.add(
                "date_not_in_sources",
                f"The date '{date}' does not appear in any source",
                QCSeverity.BLOCKER,
                detail=date,
            )

    # --- hallucination / unsupported vocabulary -------------------------
    report.checks_run.append("grounding")
    if grounding_rejected:
        report.add(
            "facts_rejected_by_grounding",
            f"{grounding_rejected} proposed fact(s) were not supported by the sources",
            QCSeverity.WARNING,
            detail=str(grounding_rejected),
        )
    summary_tokens = tokenize(summary)
    if summary_tokens:
        unsupported = [t for t in summary_tokens if t not in corpus_tokens]
        ratio = len(unsupported) / len(summary_tokens)
        if ratio > 0.25:
            report.add(
                "summary_vocabulary_unsupported",
                "A quarter or more of the summary's content words are absent from the sources",
                QCSeverity.BLOCKER,
                detail=", ".join(unsupported[:8]),
            )

    # --- opinionated / sensational language -----------------------------
    report.checks_run.append("style")
    for target, label in ((headline, "headline"), (summary, "summary")):
        # In a credited quotation the outlet is the one making the allegation,
        # and the card says so; the same words in Briefly's own voice would
        # need a named speaker.
        style = style_check(target, require_attribution_for_allegations=not quoted)
        for finding in style.findings:
            report.add(
                f"style_{finding.code}",
                f"{label}: {finding.message}",
                QCSeverity.BLOCKER if finding.severity == "blocker" else QCSeverity.WARNING,
                detail=", ".join(finding.matches[:6]),
            )

    # --- unattributed claims --------------------------------------------
    report.checks_run.append("attribution")
    for fact in facts:
        if fact.kind in {"attributed", "disputed"} and not fact.attributed_to:
            report.add(
                "fact_missing_attribution",
                "An attributed or disputed fact has no named source",
                QCSeverity.WARNING,
                detail=fact.text[:80],
            )

    # --- excessive copying ----------------------------------------------
    # n=7: two outlets reporting "the repo rate remains at 6.5 per cent" will
    # inevitably share five consecutive words, because that is the fact. A run
    # of seven or more is the publisher's sentence, not the fact.
    if quoted:
        # A quotation is supposed to match its source — so the gate flips. The
        # failures here are a quote with no name on it, and a quote that is not
        # what the outlet actually wrote.
        report.checks_run.append("quotation")
        if wording_document is None or not wording_document.source_name:
            report.add(
                "quote_not_credited",
                "The summary is a quotation but no outlet is credited with it",
                QCSeverity.BLOCKER,
            )
        elif summary and not is_verbatim(summary, wording_document.summary):
            report.add(
                "misquote",
                f"The quoted summary is not word for word what {wording_document.source_name} "
                "published",
                QCSeverity.BLOCKER,
                detail=wording_document.source_name,
            )
    else:
        report.checks_run.append("copying")
        for doc in documents:
            overlap = shingle_overlap(summary, f"{doc.headline}. {doc.summary}", n=7)
            if overlap > settings.qc_max_source_overlap:
                report.add(
                    "excessive_source_overlap",
                    f"Summary reuses {overlap:.0%} of {doc.source_name}'s wording",
                    QCSeverity.BLOCKER,
                    detail=doc.source_name,
                )
                break

    # --- duplicates ------------------------------------------------------
    report.checks_run.append("duplicates")
    for other in existing_headlines or []:
        if _near_duplicate(headline, other):
            report.add(
                "duplicate_story",
                "A very similar story is already published",
                QCSeverity.BLOCKER,
                detail=other[:100],
            )
            break

    return report


def _repeats_itself(text: str, n: int = 4) -> bool:
    """True when any run of ``n`` words occurs twice in the text."""
    tokens = tokenize(text, drop_stopwords=False, min_len=1)
    seen: set[tuple[str, ...]] = set()
    for i in range(len(tokens) - n + 1):
        gram = tuple(tokens[i : i + n])
        if gram in seen:
            return True
        seen.add(gram)
    return False


def _says_no_more_than(summary: str, headline: str) -> bool:
    """Is the summary just the headline again, give or take a word?"""
    a, b = set(tokenize(summary)), set(tokenize(headline))
    if not a or not b:
        return False
    return len(a - b) <= 1 and len(a & b) / len(a) >= 0.85


def _near_duplicate(a: str, b: str, threshold: float = 0.82) -> bool:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= threshold


_SENTENCE_KEY = re.compile(r"[^a-z0-9 ]+")


def check_script(
    *,
    script: str,
    documents: list[SourceDocument],
    target_seconds: tuple[int, int],
    words_per_minute: int = 150,
    allowed_numbers: set[str] | None = None,
) -> QCReport:
    """Gates for generated podcast narration.

    The narration legitimately contains three things no publisher wrote: the
    show's own framing, the names of the outlets it credits, and counts Briefly
    derives from its own data ("four independent outlets"). Each is allowed
    explicitly; everything else must still trace back to a source.
    """
    from app.podcast.narrator import FRAMING_VOCABULARY

    settings = get_settings()
    report = QCReport()
    corpus = _corpus(documents)
    corpus_tokens = set(tokenize(corpus)) | set(FRAMING_VOCABULARY)
    corpus_numbers = _numbers_in(corpus) | (allowed_numbers or set())
    corpus_norm = _normalised(corpus)
    publisher_names = {_normalised(d.source_name) for d in documents}
    # Tokenise rather than split: "Press Information Bureau (Government of India)"
    # must yield "government", not "(government".
    publisher_words = {w for name in publisher_names for w in tokenize(name, drop_stopwords=False)}
    corpus_tokens |= publisher_words

    report.checks_run.append("duration")
    words = count_words(script)
    seconds = int(words / words_per_minute * 60)
    lo, hi = target_seconds
    if seconds < lo * 0.6:
        report.add(
            "script_too_short",
            f"Narration is about {seconds}s; the target window starts at {lo}s",
            QCSeverity.WARNING,
            detail=str(seconds),
        )
    elif seconds > hi * 1.25:
        report.add(
            "script_too_long",
            f"Narration is about {seconds}s; the target window ends at {hi}s",
            QCSeverity.WARNING,
            detail=str(seconds),
        )

    report.checks_run.append("numbers")
    for number in _numbers_in(script):
        if number not in corpus_numbers:
            report.add(
                "number_not_in_sources",
                f"The figure {number} is not in any source",
                QCSeverity.BLOCKER,
                detail=number,
            )

    report.checks_run.append("names")
    for name in _proper_nouns(script):
        lowered = name.lower()
        if lowered in corpus_norm or lowered in publisher_words:
            continue
        if lowered in FRAMING_VOCABULARY:
            continue
        report.add(
            "name_not_in_sources",
            f"'{name}' is not in any source",
            QCSeverity.BLOCKER,
            detail=name,
        )

    report.checks_run.append("repetition")
    sentences = [
        _SENTENCE_KEY.sub("", s.lower()).strip() for s in split_sentences(script)
    ]
    seen: set[str] = set()
    for sentence in sentences:
        if len(sentence.split()) < 5:
            continue
        if sentence in seen:
            report.add(
                "repeated_sentence",
                "The same sentence appears more than once",
                QCSeverity.WARNING,
                detail=sentence[:80],
            )
            break
        seen.add(sentence)

    report.checks_run.append("style")
    style = style_check(script)
    for finding in style.findings:
        report.add(
            f"style_{finding.code}",
            finding.message,
            QCSeverity.BLOCKER if finding.severity == "blocker" else QCSeverity.WARNING,
            detail=", ".join(finding.matches[:6]),
        )

    report.checks_run.append("copying")
    for doc in documents:
        overlap = shingle_overlap(script, f"{doc.headline}. {doc.summary}", n=8)
        if overlap > settings.qc_max_source_overlap:
            report.add(
                "excessive_source_overlap",
                f"Narration reuses {overlap:.0%} of {doc.source_name}'s wording",
                QCSeverity.BLOCKER,
                detail=doc.source_name,
            )
            break

    report.checks_run.append("grounding")
    toks = tokenize(script)
    if toks:
        unsupported = [t for t in toks if t not in corpus_tokens]
        # Narration legitimately adds connective and framing words, so the bar
        # here is looser than for a 30-word card.
        if len(unsupported) / len(toks) > 0.45:
            report.add(
                "script_vocabulary_unsupported",
                "Too much of the narration is not traceable to the sources",
                QCSeverity.BLOCKER,
                detail=", ".join(unsupported[:10]),
            )

    return report


_SENTENCE_START = re.compile(r"(?:^|[.!?]\s+|[;:]\s+)")


def _proper_nouns(text: str) -> set[str]:
    """Capitalised words that are not merely starting a sentence.

    Flagging every capitalised token treats "First," and "Now" as invented
    names. A word only counts as a name when it appears capitalised somewhere
    other than the start of a sentence.
    """
    text = text or ""
    starts: set[int] = set()
    for match in _SENTENCE_START.finditer(text):
        starts.add(match.end())
    starts.add(0)
    found: set[str] = set()
    for match in _CAP_TOKEN_RE.finditer(text):
        if match.start() in starts:
            continue
        found.add(match.group(0))
    return found
