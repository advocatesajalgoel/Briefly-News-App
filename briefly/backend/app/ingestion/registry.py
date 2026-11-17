"""Load the source / category registry from data files into the database."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BACKEND_ROOT
from app.models import Category, Source

DATA_DIR = BACKEND_ROOT / "data"
SOURCES_FILE = DATA_DIR / "sources.json"
CATEGORIES_FILE = DATA_DIR / "categories.json"


def load_sources_file(path: Path | None = None) -> dict:
    return json.loads((path or SOURCES_FILE).read_text("utf-8"))


def load_categories_file(path: Path | None = None) -> dict:
    return json.loads((path or CATEGORIES_FILE).read_text("utf-8"))


def sync_categories(db: Session, path: Path | None = None) -> list[Category]:
    payload = load_categories_file(path)
    out: list[Category] = []
    for row in payload["categories"]:
        existing = db.scalar(select(Category).where(Category.slug == row["slug"]))
        if existing is None:
            existing = Category(slug=row["slug"])
            db.add(existing)
        existing.name = row["name"]
        existing.description = row.get("description")
        existing.sort_order = row.get("sort_order", 100)
        existing.keywords = row.get("keywords", [])
        existing.is_synthetic = row.get("is_synthetic", False)
        existing.is_active = row.get("is_active", True)
        out.append(existing)
    db.flush()
    return out


def sync_sources(db: Session, path: Path | None = None) -> list[Source]:
    payload = load_sources_file(path)
    out: list[Source] = []
    for row in payload["sources"]:
        existing = db.scalar(select(Source).where(Source.slug == row["slug"]))
        if existing is None:
            existing = Source(slug=row["slug"])
            db.add(existing)
        existing.name = row["name"]
        existing.homepage_url = row.get("homepage_url")
        existing.feed_url = row.get("feed_url")
        existing.domains = row.get("domains", [])
        existing.kind = row.get("kind", "other")
        existing.access = row.get("access", "feed_headline")
        existing.country = row.get("country")
        existing.language = row.get("language", "en")
        existing.is_independent = row.get("is_independent", True)
        existing.is_enabled = row.get("enabled", True)
        existing.fetch_interval_minutes = row.get("fetch_interval_minutes", 20)
        existing.notes = row.get("notes")
        out.append(existing)
    db.flush()
    return out


def discovery_queries(path: Path | None = None) -> list[dict]:
    return load_sources_file(path).get("discovery_queries", [])


def feed_plan(path: Path | None = None) -> dict[str, list[tuple[str, str | None]]]:
    """Every feed to poll for each publisher: ``slug -> [(url, category or None)]``.

    A publisher's main feed comes first, then any section feeds. The category
    is the publisher's own filing of the item — its business desk put it in the
    business feed — and is passed along as a hint, not a verdict: a story's
    section is still decided by all the reports of it together.
    """
    plan: dict[str, list[tuple[str, str | None]]] = {}
    for row in load_sources_file(path)["sources"]:
        feeds: list[tuple[str, str | None]] = []
        if row.get("feed_url"):
            feeds.append((row["feed_url"], row.get("feed_category")))
        for extra in row.get("section_feeds", []) or []:
            url = (extra.get("url") or "").strip()
            if url and all(url != known for known, _ in feeds):
                feeds.append((url, extra.get("category")))
        plan[row["slug"]] = feeds
    return plan


def source_for_domain(db: Session, domain: str) -> Source | None:
    """Find the publisher that owns ``domain`` (used to credit aggregator hits)."""
    domain = (domain or "").lower().removeprefix("www.")
    if not domain:
        return None
    for source in db.scalars(select(Source)).all():
        for known in source.domains or []:
            known = known.lower().removeprefix("www.")
            if domain == known or domain.endswith("." + known):
                return source
    return None
