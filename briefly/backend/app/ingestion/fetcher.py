"""Polite HTTP feed fetching.

Rules baked in, not configurable:
  * identify ourselves honestly with a contactable User-Agent
  * ask robots.txt first, and skip when the answer is no or unknown
  * honour ``Crawl-delay``
  * conditional GET (ETag / If-Modified-Since) so we do not re-download feeds
  * back off on failures instead of hammering
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.ingestion import robots
from app.ingestion.models import FetchResult, RawArticle
from app.ingestion.parser import parse_feed_bytes


@dataclass
class FeedState:
    """Caching hints from the previous fetch of a feed."""

    etag: str | None = None
    last_modified: str | None = None


class FeedFetcher:
    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=settings.http_timeout_seconds,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
            },
            follow_redirects=True,
        )
        self._last_request_at: dict[str, float] = {}

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> FeedFetcher:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- politeness -------------------------------------------------------
    def _respect_crawl_delay(self, url: str) -> None:
        delay = robots.crawl_delay(url)
        if not delay:
            return
        host = httpx.URL(url).host or ""
        last = self._last_request_at.get(host)
        if last is not None:
            wait = delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(min(wait, 10.0))
        self._last_request_at[host] = time.monotonic()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        reraise=True,
    )
    def _get(self, url: str, headers: dict[str, str]) -> httpx.Response:
        return self.client.get(url, headers=headers)

    # -- public -----------------------------------------------------------
    def fetch(
        self,
        feed_url: str,
        *,
        source_slug: str,
        source_name: str,
        state: FeedState | None = None,
        discovery_channel: str = "publisher_feed",
        discovery_query: str | None = None,
        limit: int | None = None,
    ) -> FetchResult:
        settings = get_settings()
        limit = limit or settings.max_articles_per_feed

        permission = robots.decide(feed_url, client=self.client)
        if not permission.allowed:
            # The reason is specific — which rule, or which failure — because
            # "disallowed or could not be read" told nobody which of two very
            # different things had happened.
            return FetchResult(feed_url=feed_url, ok=False, skipped_reason=permission.reason)

        headers: dict[str, str] = {}
        if state and state.etag:
            headers["If-None-Match"] = state.etag
        if state and state.last_modified:
            headers["If-Modified-Since"] = state.last_modified

        self._respect_crawl_delay(feed_url)
        try:
            resp = self._get(feed_url, headers)
        except Exception as exc:  # network-level failure
            return FetchResult(feed_url=feed_url, ok=False, error=f"{type(exc).__name__}: {exc}")

        if resp.status_code == 304:
            return FetchResult(
                feed_url=feed_url,
                ok=True,
                status_code=304,
                skipped_reason="not modified since last fetch",
                etag=state.etag if state else None,
                last_modified=state.last_modified if state else None,
            )
        if resp.status_code == 429:
            return FetchResult(
                feed_url=feed_url, ok=False, status_code=429,
                error="rate limited by publisher; backing off",
            )
        if resp.status_code in (401, 402, 403):
            return FetchResult(
                feed_url=feed_url, ok=False, status_code=resp.status_code,
                error="access restricted by publisher; not attempting to work around it",
            )
        if resp.status_code >= 400:
            return FetchResult(
                feed_url=feed_url, ok=False, status_code=resp.status_code,
                error=f"HTTP {resp.status_code}",
            )

        articles: list[RawArticle] = parse_feed_bytes(
            resp.content,
            source_slug=source_slug,
            source_name=source_name,
            discovery_channel=discovery_channel,
            discovery_query=discovery_query,
            limit=limit,
        )
        return FetchResult(
            feed_url=feed_url,
            ok=True,
            status_code=resp.status_code,
            articles=articles,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
        )
