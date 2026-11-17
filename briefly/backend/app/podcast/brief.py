"""The story brief — the structured view both narrators work from."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SourceRef:
    name: str
    kind: str
    headline: str
    url: str
    published_at: datetime | None = None
    is_primary: bool = False

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "headline": self.headline,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "is_primary": self.is_primary,
        }


@dataclass
class FactRef:
    slot: str
    kind: str
    text: str
    attributed_to: str | None = None
    support_count: int = 1

    def as_dict(self) -> dict:
        return {
            "slot": self.slot,
            "kind": self.kind,
            "text": self.text,
            "attributed_to": self.attributed_to,
            "support_count": self.support_count,
        }


@dataclass
class StoryBrief:
    story_id: str
    headline: str
    summary: str
    dek: str = ""
    category: str = ""
    category_name: str = ""
    published_at: datetime | None = None
    source_count: int = 0
    independent_source_count: int = 0
    has_official_source: bool = False
    has_disputed_claims: bool = False
    diversity_level: str = "low"
    diversity_lines: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    facts: list[FactRef] = field(default_factory=list)

    # -- convenience views -------------------------------------------------
    def by_kind(self, kind: str) -> list[FactRef]:
        return [f for f in self.facts if f.kind == kind]

    def by_slot(self, slot: str) -> list[FactRef]:
        return [f for f in self.facts if f.slot == slot]

    @property
    def confirmed(self) -> list[FactRef]:
        return self.by_kind("confirmed")

    @property
    def attributed(self) -> list[FactRef]:
        return self.by_kind("attributed")

    @property
    def disputed(self) -> list[FactRef]:
        return self.by_kind("disputed")

    @property
    def uncertain(self) -> list[FactRef]:
        return self.by_kind("uncertain")

    @property
    def numbers(self) -> list[FactRef]:
        return self.by_slot("number")

    @property
    def source_names(self) -> list[str]:
        return [s.name for s in self.sources]

    def as_dict(self) -> dict:
        return {
            "story_id": self.story_id,
            "headline": self.headline,
            "summary": self.summary,
            "dek": self.dek,
            "category": self.category,
            "category_name": self.category_name,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "source_count": self.source_count,
            "independent_source_count": self.independent_source_count,
            "has_official_source": self.has_official_source,
            "has_disputed_claims": self.has_disputed_claims,
            "diversity_level": self.diversity_level,
            "diversity_lines": self.diversity_lines,
            "sources": [s.as_dict() for s in self.sources],
            "facts": [f.as_dict() for f in self.facts],
        }

    @classmethod
    def from_dict(cls, data: dict) -> StoryBrief:
        return cls(
            story_id=str(data.get("story_id", "")),
            headline=data.get("headline", ""),
            summary=data.get("summary", ""),
            dek=data.get("dek", ""),
            category=data.get("category", ""),
            category_name=data.get("category_name", ""),
            source_count=int(data.get("source_count", 0)),
            independent_source_count=int(data.get("independent_source_count", 0)),
            has_official_source=bool(data.get("has_official_source", False)),
            has_disputed_claims=bool(data.get("has_disputed_claims", False)),
            diversity_level=data.get("diversity_level", "low"),
            diversity_lines=list(data.get("diversity_lines", [])),
            sources=[
                SourceRef(
                    name=s.get("name", ""),
                    kind=s.get("kind", "other"),
                    headline=s.get("headline", ""),
                    url=s.get("url", ""),
                    is_primary=bool(s.get("is_primary", False)),
                )
                for s in data.get("sources", [])
            ],
            facts=[
                FactRef(
                    slot=f.get("slot", "other"),
                    kind=f.get("kind", "attributed"),
                    text=f.get("text", ""),
                    attributed_to=f.get("attributed_to"),
                    support_count=int(f.get("support_count", 1)),
                )
                for f in data.get("facts", [])
            ],
        )
