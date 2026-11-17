"""Fact extraction with grounding verification.

Extraction backends propose; this module disposes. Whatever the backend is —
the deterministic rule-based one or a hosted model — every proposed fact must
be traceable to the material that was actually supplied. A fact that cannot be
traced is dropped and recorded, never published.

The checks:

* **evidence span** — the fact carries a verbatim snippet; it must appear in the
  corpus (whitespace/case-insensitive).
* **numbers** — every figure in the fact text must appear in the corpus. A model
  that rounds 4.6 to 5 fails here.
* **names** — every capitalised token in the fact text must appear in the corpus.
* **vocabulary coverage** — at least 70% of the fact's content words must occur
  in the corpus, which catches invented clauses attached to real names.
* **attribution** — an attributed fact must name a speaker that appears in the
  corpus or is one of the supplied publishers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.llm.schema import ExtractionResult, FactCandidate, SourceDocument
from app.text.normalize import clean_text, extract_numbers, tokenize
from app.text.wordcount import normalise_whitespace

_CAP_TOKEN_RE = re.compile(r"\b[A-Z][a-zA-Z’'\-]{2,}\b")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")

MIN_VOCAB_COVERAGE = 0.70


@dataclass
class GroundingIssue:
    fact_text: str
    reason: str
    detail: str = ""


@dataclass
class GroundingReport:
    kept: list[FactCandidate] = field(default_factory=list)
    rejected: list[GroundingIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.kept)

    def as_dict(self) -> dict:
        return {
            "kept": len(self.kept),
            "rejected": [
                {"text": r.fact_text, "reason": r.reason, "detail": r.detail}
                for r in self.rejected
            ],
        }


def _corpus(documents: list[SourceDocument]) -> str:
    return " \n ".join(f"{d.headline}. {d.summary}" for d in documents)


def _normalised(text: str) -> str:
    return re.sub(r"\s+", " ", clean_text(text or "")).lower()


def _numbers_in(text: str) -> set[str]:
    """Digits only, punctuation-insensitive: 1,200 and 1200 are the same figure."""
    return {m.group(0).replace(",", "").rstrip(".") for m in _NUM_RE.finditer(text or "")}


def verify_fact(
    fact: FactCandidate,
    corpus_norm: str,
    corpus_tokens: set[str],
    corpus_numbers: set[str],
    publisher_names: set[str],
) -> GroundingIssue | None:
    text = normalise_whitespace(fact.text)
    if not text:
        return GroundingIssue(fact.text, "empty_fact")

    # 1. evidence span
    if fact.evidence:
        if _normalised(fact.evidence) not in corpus_norm:
            return GroundingIssue(
                fact.fact_text if hasattr(fact, "fact_text") else fact.text,
                "evidence_not_found",
                fact.evidence[:160],
            )

    # 2. numbers
    for number in _numbers_in(text):
        if number not in corpus_numbers:
            return GroundingIssue(text, "number_not_in_sources", number)

    # 3. capitalised names
    lowered_corpus = corpus_norm
    for name in set(_CAP_TOKEN_RE.findall(text)):
        if name.lower() not in lowered_corpus:
            return GroundingIssue(text, "name_not_in_sources", name)

    # 4. vocabulary coverage
    toks = tokenize(text)
    if toks:
        covered = sum(1 for t in toks if t in corpus_tokens)
        coverage = covered / len(toks)
        if coverage < MIN_VOCAB_COVERAGE:
            return GroundingIssue(text, "low_vocabulary_coverage", f"{coverage:.2f}")

    # 5. attribution must point at somebody the material mentions
    if fact.attributed_to:
        who = _normalised(fact.attributed_to)
        if who and who not in lowered_corpus and who not in publisher_names:
            return GroundingIssue(text, "attribution_not_in_sources", fact.attributed_to)

    return None


def verify_grounding(
    facts: list[FactCandidate], documents: list[SourceDocument]
) -> GroundingReport:
    corpus = _corpus(documents)
    corpus_norm = _normalised(corpus)
    corpus_tokens = set(tokenize(corpus))
    corpus_numbers = _numbers_in(corpus) | {
        n.replace(",", "") for n in extract_numbers(corpus, limit=200)
    }
    publisher_names = {_normalised(d.source_name) for d in documents}

    report = GroundingReport()
    for fact in facts:
        issue = verify_fact(fact, corpus_norm, corpus_tokens, corpus_numbers, publisher_names)
        if issue is None:
            report.kept.append(fact)
        else:
            report.rejected.append(issue)
    return report


def extract_facts(
    documents: list[SourceDocument], provider=None
) -> tuple[ExtractionResult, GroundingReport]:
    """Run the configured backend and keep only what the sources support."""
    from app.llm.factory import get_extraction_provider

    provider = provider or get_extraction_provider()
    result = provider.extract(documents)
    report = verify_grounding(result.facts, documents)
    result.facts = report.kept
    if report.rejected:
        result.warnings.append(
            f"{len(report.rejected)} proposed fact(s) dropped for lack of support"
        )

    # Rebuild the card clauses from corroborated facts only, regardless of
    # which extraction provider ran. Attributed, disputed and uncertain claims
    # stay in the source transparency panel and are never blended into the card.
    from app.llm.rule_based import build_summary_clauses

    confirmed = [fact for fact in result.facts if fact.kind == "confirmed"]
    result.summary_clauses = build_summary_clauses(confirmed, documents, result.headline)
    return result, report
