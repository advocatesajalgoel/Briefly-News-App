"""feedparser entry -> RawArticle."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse
from datetime import UTC, datetime

import feedparser

from app.ingestion.models import RawArticle
from app.text.boilerplate import repeated_sentences, strip_repeated
from app.text.normalize import canonical_url, clean_text

# How much of a publisher's syndicated blurb we keep. Feeds are meant to be
# read, but we store only what the extraction step needs and never a full body.
MAX_FEED_SUMMARY_CHARS = 900
MAX_HEADLINE_CHARS = 300


def url_hash(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()


def _parse_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                continue
    return None


def _entry_summary(entry) -> str:
    for key in ("summary", "description"):
        if entry.get(key):
            return clean_text(entry[key], max_chars=MAX_FEED_SUMMARY_CHARS)
    content = entry.get("content")
    if content:
        try:
            return clean_text(content[0].get("value", ""), max_chars=MAX_FEED_SUMMARY_CHARS)
        except (AttributeError, IndexError, KeyError):
            pass
    return ""


def _entry_image(entry) -> str | None:
    """Publisher-supplied feed image only; never manufacture or hotlink search results."""
    candidates: list[str] = []
    for item in entry.get("media_content", []) or []:
        if item.get("url") and (item.get("medium") == "image" or
                                str(item.get("type", "")).startswith("image/")):
            candidates.append(item["url"])
    for item in entry.get("media_thumbnail", []) or []:
        if item.get("url"):
            candidates.append(item["url"])
    for item in entry.get("links", []) or []:
        if item.get("rel") == "enclosure" and str(item.get("type", "")).startswith("image/"):
            if item.get("href"):
                candidates.append(item["href"])
    # RSS descriptions commonly include the publisher's own lead image.
    for field in ("summary", "description"):
        html = entry.get(field) or ""
        match = re.search(r"<img[^>]+src=['\\\"]([^'\\\"]+)['\\\"]", html, re.I)
        if match:
            candidates.append(match.group(1))
    for value in candidates:
        if not isinstance(value, str):
            continue
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return value
    return None


def _entry_link(entry) -> str:
    link = entry.get("link") or ""
    if link:
        return link
    for candidate in entry.get("links", []) or []:
        href = candidate.get("href")
        if href:
            return href
    return ""


def parse_entry(
    entry,
    *,
    source_slug: str,
    source_name: str,
    discovery_channel: str = "publisher_feed",
    discovery_query: str | None = None,
    default_language: str = "en",
) -> RawArticle | None:
    link = _entry_link(entry)
    headline = clean_text(entry.get("title", ""), max_chars=MAX_HEADLINE_CHARS)
    if not link or not headline:
        return None

    canon = canonical_url(link)
    reported_publisher = None
    reported_publisher_url = None
    src = entry.get("source")
    if src:
        reported_publisher = clean_text(getattr(src, "title", None) or src.get("title", ""))
        reported_publisher_url = getattr(src, "href", None) or src.get("href")

    return RawArticle(
        source_slug=source_slug,
        source_name=source_name,
        url=link,
        canonical_url=canon,
        url_hash=url_hash(canon),
        headline=headline,
        feed_summary=_entry_summary(entry),
        author=clean_text(entry.get("author", "")) or None,
        guid=entry.get("id") or entry.get("guid") or None,
        published_at=_parse_time(entry),
        language=(entry.get("language") or default_language)[:12],
        discovery_channel=discovery_channel,
        discovery_query=discovery_query,
        reported_publisher=reported_publisher or None,
        reported_publisher_url=reported_publisher_url or None,
        raw={
            "tags": [t.get("term") for t in (entry.get("tags") or []) if t.get("term")],
            "feed_id": entry.get("id"),
            "image_url": _entry_image(entry),
        },
    )


def parse_feed_bytes(
    payload: bytes | str,
    *,
    source_slug: str,
    source_name: str,
    discovery_channel: str = "publisher_feed",
    discovery_query: str | None = None,
    limit: int = 60,
) -> list[RawArticle]:
    parsed = feedparser.parse(payload)
    feed_language = (parsed.feed.get("language") or "en")[:12] if parsed.get("feed") else "en"
    out: list[RawArticle] = []
    for entry in parsed.entries[:limit]:
        article = parse_entry(
            entry,
            source_slug=source_slug,
            source_name=source_name,
            discovery_channel=discovery_channel,
            discovery_query=discovery_query,
            default_language=feed_language,
        )
        if article:
            out.append(article)

    # Drop whatever this feed staples to every item — see app/text/boilerplate.
    furniture = repeated_sentences([a.feed_summary for a in out])
    if furniture:
        for article in out:
            article.feed_summary = strip_repeated(article.feed_summary, furniture)
    return out
