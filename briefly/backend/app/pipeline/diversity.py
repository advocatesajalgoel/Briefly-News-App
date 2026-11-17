"""The Source Diversity indicator.

This is a count of *where reporting came from*. It is not a bias measurement,
not a political scale, and not a scientific instrument — the app says so on the
panel that displays it. A story carried by eight outlets that all syndicate the
same wire copy is less diverse than one carried by three outlets that each sent
a reporter, and this indicator is an honest attempt to show that difference
using facts we actually have.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.enums import DiversityLevel, SourceKind


@dataclass
class SourceFacet:
    slug: str
    name: str
    kind: str
    country: str | None = None
    is_independent: bool = True


@dataclass
class DiversityResult:
    level: str
    breakdown: dict = field(default_factory=dict)
    total: int = 0
    independent: int = 0
    countries: int = 0
    has_official: bool = False

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "total": self.total,
            "independent": self.independent,
            "countries": self.countries,
            "has_official": self.has_official,
            "breakdown": self.breakdown,
        }


# Human-readable labels the app renders directly.
KIND_LABELS = {
    SourceKind.NATIONAL: "national",
    SourceKind.INTERNATIONAL: "international",
    SourceKind.REGIONAL: "regional",
    SourceKind.WIRE: "wire service",
    SourceKind.OFFICIAL: "official",
    SourceKind.OTHER: "other",
}


def compute_diversity(facets: list[SourceFacet]) -> DiversityResult:
    facets = [f for f in facets if f.kind != SourceKind.AGGREGATOR]
    if not facets:
        return DiversityResult(level=DiversityLevel.LOW, breakdown={}, total=0)

    kinds = Counter(KIND_LABELS.get(f.kind, f.kind) for f in facets)
    countries = Counter(f.country or "unknown" for f in facets)
    independent = sum(1 for f in facets if f.is_independent)
    has_official = any(f.kind == SourceKind.OFFICIAL for f in facets)

    distinct_kinds = len([k for k, c in kinds.items() if c])
    distinct_countries = len([c for c in countries if c != "unknown"])

    # A simple, explainable score. Every term is something a reader can verify
    # from the source list shown right underneath the indicator.
    score = 0.0
    score += min(independent, 8) / 8 * 0.45          # how many independent newsrooms
    score += min(distinct_kinds, 4) / 4 * 0.25        # how many *sorts* of outlet
    score += min(distinct_countries, 3) / 3 * 0.20    # how many countries
    score += 0.10 if has_official else 0.0            # a primary source present

    if score >= 0.62 and independent >= 4:
        level = DiversityLevel.HIGH
    elif score >= 0.34 and independent >= 2:
        level = DiversityLevel.MEDIUM
    else:
        level = DiversityLevel.LOW

    return DiversityResult(
        level=level,
        total=len(facets),
        independent=independent,
        countries=distinct_countries,
        has_official=has_official,
        breakdown={
            "by_kind": dict(kinds),
            "by_country": dict(countries),
            "score": round(score, 3),
        },
    )


def describe(result: DiversityResult) -> list[str]:
    """Lines the app shows under the SOURCE DIVERSITY heading.

    The first lines split the sources by country, so they add up to the total.
    The lines after them describe *the same* sources a second way — a
    government press office is also an Indian source — and are therefore
    written as "including", never as though they were further entries in the
    same tally. A five-source story whose panel lists four, one and one reads
    as six sources; a panel about transparency cannot afford that.
    """
    lines: list[str] = []
    countries = result.breakdown.get("by_country", {})

    india = countries.get("IN")
    if india:
        lines.append(f"{india} Indian source{'s' if india != 1 else ''}")
    intl = sum(v for k, v in countries.items() if k not in {"IN", "unknown"})
    if intl:
        lines.append(f"{intl} international source{'s' if intl != 1 else ''}")
    unknown = countries.get("unknown")
    if unknown:
        lines.append(
            f"{unknown} source{'s' if unknown != 1 else ''} of unstated origin"
        )

    by_kind = result.breakdown.get("by_kind", {})
    for label, noun in (
        ("regional", "regional outlet"),
        ("wire service", "wire service"),
        ("official", "official source"),
    ):
        n = by_kind.get(label)
        if n:
            lines.append(f"including {n} {noun}{'s' if n != 1 else ''}")
    return lines
