#!/usr/bin/env python3
"""Render the published stories and episodes as a static site.

This is what makes Briefly work on a phone with no server at all. A scheduled
GitHub Actions run does the whole pipeline on a free Linux runner, calls this
script, and commits the result. GitHub Pages then serves it, and the web app
reads plain JSON from its own origin — so there is no host to pay for, no CORS
proxy, and no API key anywhere.

    python -m scripts.export_static_site [--out ../site]

Writes:
    site/api/stories.json     every published story, ranked
    site/api/categories.json  the sections
    site/api/episodes.json    podcast episodes, audio rewritten to local paths
    site/api/status.json      when this was built, from how many sources, and
                              whether it is live news or the sample stories
    site/media/...            the generated audio
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from urllib.parse import urlsplit  # noqa: E402

from app.config import REPO_ROOT, get_settings  # noqa: E402
from app.ingestion.registry import load_sources_file  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "site"


def is_sample(stories: list[dict]) -> bool:
    """True when every link in the build points at the reserved ``.test`` domain.

    That domain cannot resolve and cannot occur in real news, so it identifies
    the built-in sample stories without anyone having to remember to pass a
    flag — which matters, because the one time the flag would be forgotten is
    the one time the site is about to present invented stories as today's news.
    """
    hosts = [
        urlsplit(source.get("original_url") or "").hostname or ""
        for story in stories
        for source in story.get("sources", [])
    ]
    return bool(hosts) and all(host.endswith(".test") for host in hosts)


def real_publishers_named(payload: object) -> list[str]:
    """Registry publishers whose names appear anywhere in ``payload``."""
    text = json.dumps(payload, ensure_ascii=False)
    names = [row["name"] for row in load_sources_file()["sources"] if row.get("name")]
    return sorted(name for name in names if name in text and name != "Google News")


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    size = path.stat().st_size
    print(f"  {path.relative_to(path.parent.parent.parent)}  {size // 1024 or 1} KB")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=60,
                        help="how many stories to publish in the ranked mix")
    parser.add_argument("--per-section", type=int, default=20,
                        help="also publish up to this many stories from each section")
    parser.add_argument("--run-stats", default=None,
                        help="JSON printed by the pipeline run, for the status file")
    args = parser.parse_args()

    out = Path(args.out)
    api = out / "api"
    media = out / "media"

    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())

    print("Exporting static site…")

    categories = client.get("/v1/categories").json()
    _write(api / "categories.json", categories)

    stories = client.get(f"/v1/stories?limit={min(args.limit, 50)}").json()
    # The read API caps a page at 50; page through for anything larger.
    items = stories["items"]
    cursor = stories.get("next_cursor")
    while cursor and len(items) < args.limit:
        page = client.get(f"/v1/stories?limit=50&cursor={cursor}").json()
        items.extend(page["items"])
        cursor = page.get("next_cursor")
    items = items[: args.limit]

    # The ranked mix on its own starves the smaller sections: on a day of heavy
    # politics the top sixty stories can hold no science at all, and the Science
    # tab would say "nothing here" while the pipeline holds a dozen. So each
    # section also contributes its own best stories.
    held = {story["id"] for story in items}
    for category in categories:
        slug = category.get("slug")
        if not slug or category.get("is_synthetic") or slug == "for-you":
            continue
        page = client.get(f"/v1/stories?category={slug}&limit={min(args.per_section, 50)}")
        if page.status_code != 200:
            continue
        for story in page.json().get("items", []):
            if story["id"] not in held:
                held.add(story["id"])
                items.append(story)
    items.sort(key=lambda story: -(story.get("rank_score") or 0.0))

    stories["items"] = items
    stories["next_cursor"] = None

    sample = is_sample(items)
    _write(api / "stories.json", stories)

    settings = get_settings()
    episodes = client.get("/v1/podcast/episodes?limit=20").json()
    for episode in episodes.get("items", []):
        detail = client.get(f"/v1/podcast/episodes/{episode['id']}")
        if detail.status_code == 200:
            episode.update(detail.json())

        url = episode.get("audio_url") or ""
        if "/media/" not in url:
            continue
        key = url.split("/media/", 1)[1]
        source = settings.media_dir / key
        if not source.exists():
            episode["audio_url"] = None
            continue
        target = media / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        # Relative, so the site works under a project path such as
        # https://name.github.io/briefly/ as well as at a domain root.
        episode["audio_url"] = f"media/{key}"
        episode["audio_bytes"] = target.stat().st_size
    _write(api / "episodes.json", episodes)

    by_section: dict[str, int] = {}
    publishers: set[str] = set()
    for story in stories["items"]:
        slug = story.get("category_slug") or "other"
        by_section[slug] = by_section.get(slug, 0) + 1
        for source in story.get("sources", []):
            publishers.add(source["source_name"])

    if sample:
        # Sample stories are filed under invented outlets before the pipeline
        # reads them. If a real publisher's name is in this build anyway,
        # something upstream has changed, and publishing would put an invented
        # story under a real masthead. Stop instead.
        leaked = real_publishers_named([stories, episodes])
        if leaked:
            raise SystemExit(
                "refusing to export: sample stories name real publishers: "
                + ", ".join(leaked)
            )

    feeds: dict = {}
    if args.run_stats and Path(args.run_stats).exists():
        try:
            ingest = json.loads(Path(args.run_stats).read_text("utf-8")).get("ingest", {})
            feeds = {
                key: ingest.get(key)
                for key in ("feeds_attempted", "feeds_ok", "feeds_failed", "feeds_skipped")
                if ingest.get(key) is not None
            }
        except (ValueError, OSError):
            feeds = {}

    _write(api / "status.json", {
        "built_at": datetime.now(UTC).isoformat(),
        "sample": sample,
        "stories": len(stories["items"]),
        "episodes": len(episodes.get("items", [])),
        "publishers": sorted(publishers),
        "publisher_count": len(publishers),
        "by_section": by_section,
        "feeds": feeds,
        "llm_provider": settings.llm_provider,
        "tts_provider": settings.tts_provider,
    })

    # Per-publisher collection health. A domain-search result is discovery,
    # not proof of a successful direct publisher feed; keep those metrics apart.
    run_data = {}
    if args.run_stats and Path(args.run_stats).exists():
        try:
            run_data = json.loads(Path(args.run_stats).read_text("utf-8"))
        except (ValueError, OSError):
            run_data = {}
    ingest_data = run_data.get("ingest", {})
    feed_rows = ingest_data.get("feeds", []) or []
    source_rows = [
        row for row in load_sources_file().get("sources", [])
        if row.get("slug") in {
            "scroll-in", "the-wire", "theprint", "newslaundry", "the-quint",
            "the-news-minute", "article-14", "reporters-collective", "the-caravan",
            "pari", "the-federal", "eastmojo", "boom-live", "alt-news", "factly",
        }
    ]
    health_sources = []
    for source in source_rows:
        slug = source["slug"]
        domain = (source.get("domains") or [""])[0]
        direct = [f for f in feed_rows if f.get("source") == slug]
        discovery = [
            f for f in feed_rows
            if f.get("source") == "google-news"
            and f.get("query")
            and domain
            and f"site:{domain}" in f.get("query", "")
        ]
        attempts = direct + discovery
        articles_count = sum(
            1 for story in stories["items"]
            for item in story.get("sources", [])
            if item.get("source_name") == source.get("name")
        )
        if any(f.get("status") == "ok" for f in direct):
            health_status = "direct_feed_working"
        elif any(f.get("status") == "ok" for f in discovery):
            health_status = "discovery_working"
        elif attempts and all(f.get("status") == "failed" for f in attempts):
            health_status = "failed"
        elif attempts:
            health_status = "restricted_or_skipped"
        else:
            health_status = "not_checked"
        health_sources.append({
            "slug": slug,
            "name": source.get("name"),
            "status": health_status,
            "enabled": bool(source.get("enabled")),
            "methods": (["publisher_rss"] if source.get("feed_url") else [])
                       + (["publisher_domain_search"] if domain else []),
            "direct_feed": direct[-1] if direct else None,
            "discovery": discovery[-1] if discovery else None,
            "articles_published": articles_count,
        })
    _write(api / "source-health.json", {
        "built_at": datetime.now(UTC).isoformat(),
        "sources": health_sources,
        "summary": {
            "publishers_configured": len(health_sources),
            "direct_feed_working": sum(x["status"] == "direct_feed_working" for x in health_sources),
            "discovery_working": sum(x["status"] == "discovery_working" for x in health_sources),
            "failed": sum(x["status"] == "failed" for x in health_sources),
            "not_checked": sum(x["status"] == "not_checked" for x in health_sources),
            "articles_published": sum(x["articles_published"] for x in health_sources),
        },
    })

    if sample:
        print("\nNOTE: this build carries the SAMPLE stories, and says so on screen.")
    print(f"\nDone. {len(stories['items'])} stories, "
          f"{len(episodes.get('items', []))} episodes, "
          f"{len(publishers)} publishers → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
