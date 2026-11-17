"""The contract every extraction backend must satisfy."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

VALID_SLOTS = {"who", "what", "when", "where", "why", "number", "date", "other"}
VALID_KINDS = {
    "confirmed", "attributed", "disputed", "number", "date", "context", "uncertain",
}


@dataclass
class SourceDocument:
    """What a backend is allowed to look at. Feed material only."""

    index: int
    source_slug: str
    source_name: str
    source_kind: str
    headline: str
    summary: str = ""
    url: str = ""
    published_at: str | None = None

    @property
    def text(self) -> str:
        return f"{self.headline}. {self.summary}".strip()


@dataclass
class FactCandidate:
    slot: str
    kind: str
    text: str
    attributed_to: str | None = None
    evidence: str | None = None
    source_index: int | None = None
    source_slug: str | None = None
    support_count: int = 1
    confidence: float = 0.5
    salience: float = 0.5
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)

    def normalised(self) -> FactCandidate:
        slot = self.slot if self.slot in VALID_SLOTS else "other"
        kind = self.kind if self.kind in VALID_KINDS else "attributed"
        return FactCandidate(
            slot=slot,
            kind=kind,
            text=(self.text or "").strip(),
            attributed_to=(self.attributed_to or None),
            evidence=(self.evidence or None),
            source_index=self.source_index,
            source_slug=self.source_slug,
            support_count=max(1, int(self.support_count)),
            confidence=min(1.0, max(0.0, float(self.confidence))),
            salience=min(1.0, max(0.0, float(self.salience))),
            extra=dict(self.extra or {}),
        )


@dataclass
class ExtractionResult:
    headline: str = ""
    dek: str = ""
    facts: list[FactCandidate] = field(default_factory=list)
    # Ranked candidate clauses for the 30-word card, highest priority first.
    summary_clauses: list[dict] = field(default_factory=list)
    provider: str = "rule_based"
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "headline": self.headline,
            "dek": self.dek,
            "facts": [f.as_dict() for f in self.facts],
            "summary_clauses": self.summary_clauses,
            "provider": self.provider,
            "warnings": self.warnings,
        }


class ExtractionProvider:
    """Interface. Implementations must never invent a fact that is not present
    in the supplied documents; the caller verifies this independently."""

    name = "base"

    def available(self) -> bool:
        return True

    def extract(self, documents: list[SourceDocument]) -> ExtractionResult:  # pragma: no cover
        raise NotImplementedError

    def write_narration(
        self, story_brief: dict, target_words: int, mode: str = "daily"
    ) -> str:  # pragma: no cover
        raise NotImplementedError
