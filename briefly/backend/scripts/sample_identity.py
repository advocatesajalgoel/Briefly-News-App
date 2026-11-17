"""Invented outlets for the invented stories.

The sample feeds describe events that never happened — a cyclone called Verath,
a city called Kalpore. Inside the test suite they are filed under the real
registry's publishers, because that is what exercises the real registry.

Anything a person will *read* is a different matter. A card that says a real
newspaper reported a story it never ran is a fabricated attribution, however
clearly the screen is labelled, and a spoken briefing has no label at all. So
whenever the sample stories are loaded for show — the bundled app data, a
demonstration build, the public site's fallback on a day no feed answers — each
real publisher is swapped for an outlet that does not exist, *before* ingestion.
The pipeline never sees the real name, so it cannot surface in a summary, a
source list, a narration script, or the audio voiced from it.

What is kept is the outlet's *kind* and country, because that is what the
Source Diversity panel is demonstrating.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.models import RawArticle
from app.ingestion.parser import url_hash
from app.models import Source
from app.text.normalize import canonical_url

# registry slug -> invented outlet
SAMPLE_OUTLETS: dict[str, str] = {
    "pib-india": "Ordelia State Press Office",
    "bbc-news": "Continental Review",
    "al-jazeera": "The Meridian Post",
    "the-guardian": "Northwatch Daily",
    "the-hindu": "The Kalpore Herald",
    "indian-express": "Ordelia Chronicle",
    "economic-times": "The Ledger",
    "times-of-india": "Ordelia Times",
    "hindustan-times": "The National Record",
    "ndtv": "Ordelia News Network",
}

SAMPLE_AGGREGATOR_FEED = "https://aggregator.test/rss"
_SLUG = re.compile(r"[^a-z0-9]+")


def outlet_slug(name: str) -> str:
    return _SLUG.sub("-", name.lower()).strip("-")


@dataclass
class Outlet:
    real_slug: str
    real_name: str
    source: Source          # the invented outlet's own row

    @property
    def host(self) -> str:
        return f"{self.source.slug}.test"

    @property
    def feed_url(self) -> str:
        return f"https://{self.host}/feed"


class SampleIdentity:
    """Creates the invented outlets and rewrites sample items to belong to them."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.outlets: dict[str, Outlet] = {}          # by real slug
        self._by_sample_slug: dict[str, Outlet] = {}

    def outlet_for(self, real: Source) -> Outlet | None:
        if real.slug in self.outlets:
            return self.outlets[real.slug]
        name = SAMPLE_OUTLETS.get(real.slug)
        if not name:
            return None
        slug = outlet_slug(name)
        row = self.db.scalar(select(Source).where(Source.slug == slug))
        if row is None:
            row = Source(slug=slug)
            self.db.add(row)
        row.name = name
        row.homepage_url = f"https://{slug}.test"
        row.feed_url = None
        row.domains = [f"{slug}.test"]
        row.kind = real.kind
        row.access = real.access
        row.country = real.country
        row.language = real.language
        row.is_independent = real.is_independent
        row.is_enabled = True
        row.notes = "Invented outlet. Exists only to carry the sample stories."
        self.db.flush()
        outlet = Outlet(real_slug=real.slug, real_name=real.name, source=row)
        self.outlets[real.slug] = outlet
        self._by_sample_slug[slug] = outlet
        return outlet

    def fixture_slug(self, sample_slug: str) -> str:
        """Which fixture file an invented outlet's items are read from."""
        outlet = self._by_sample_slug.get(sample_slug)
        return outlet.real_slug if outlet else sample_slug

    # -- rewriting -------------------------------------------------------
    def _rename(self, text: str | None) -> str | None:
        if not text:
            return text
        # Longest names first, so "The Indian Express" is not half-replaced
        # by a rule for a shorter name inside it.
        for outlet in sorted(self.outlets.values(), key=lambda o: -len(o.real_name)):
            text = text.replace(outlet.real_name, outlet.source.name)
        return text

    def _rehost(self, url: str | None) -> str | None:
        if not url:
            return url
        parts = urlsplit(url)
        for outlet in self.outlets.values():
            if parts.netloc == f"example-{outlet.real_slug}.test":
                return urlunsplit((parts.scheme, outlet.host, parts.path, parts.query, ""))
        return url

    def rewrite(self, article: RawArticle) -> RawArticle:
        article.headline = self._rename(article.headline) or ""
        article.feed_summary = self._rename(article.feed_summary) or ""
        article.reported_publisher = self._rename(article.reported_publisher)
        article.reported_publisher_url = self._rehost(article.reported_publisher_url)
        article.url = self._rehost(article.url) or article.url
        article.canonical_url = canonical_url(article.url)
        article.url_hash = url_hash(article.canonical_url)
        outlet = self._by_sample_slug.get(article.source_slug)
        if outlet is not None:
            article.source_name = outlet.source.name
        return article

    def real_names(self) -> list[str]:
        return [o.real_name for o in self.outlets.values()]
