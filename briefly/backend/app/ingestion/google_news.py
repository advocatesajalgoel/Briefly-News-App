"""Google News RSS — story *discovery* only.

Google News publishes RSS endpoints. Briefly uses them the way they are meant
to be used: to find out that something happened and which publishers filed on
it. It does not parse Google News HTML, does not decode Google's redirect
tokens, and never treats "Google News" as a source in the transparency list —
the credited publisher from the feed is the source.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from app.config import get_settings

BASE = "https://news.google.com/rss"

# Google News topic identifiers -> Briefly category slugs.
TOPIC_MAP: dict[str, str] = {
    "NATION": "india",
    "WORLD": "world",
    "BUSINESS": "business",
    "TECHNOLOGY": "technology",
    "SCIENCE": "science",
    "SPORTS": "sports",
    "ENTERTAINMENT": "entertainment",
    "HEALTH": "science",
}


def _locale_params() -> str:
    s = get_settings()
    return f"hl={s.google_news_hl}&gl={s.google_news_gl}&ceid={quote_plus(s.google_news_ceid)}"


def topic_feed_url(topic: str) -> str:
    """Headlines for one Google News topic (NATION, WORLD, BUSINESS, ...)."""
    topic = topic.upper()
    if topic not in TOPIC_MAP:
        raise ValueError(f"unknown Google News topic {topic!r}")
    return f"{BASE}/headlines/section/topic/{topic}?{_locale_params()}"


def top_stories_url() -> str:
    return f"{BASE}?{_locale_params()}"


def search_feed_url(query: str, *, when: str | None = "1d") -> str:
    """Search feed. ``when`` accepts Google's relative window, e.g. ``1d``/``7d``."""
    q = query.strip()
    if not q:
        raise ValueError("query must not be empty")
    if when:
        q = f"{q} when:{when}"
    return f"{BASE}/search?q={quote_plus(q)}&{_locale_params()}"


def default_discovery_feeds() -> list[tuple[str, str]]:
    """``(category_slug, feed_url)`` pairs Briefly polls by default."""
    feeds = [(TOPIC_MAP[t], topic_feed_url(t)) for t in ("NATION", "WORLD", "BUSINESS",
                                                          "TECHNOLOGY", "SCIENCE", "SPORTS",
                                                          "ENTERTAINMENT")]
    return feeds
