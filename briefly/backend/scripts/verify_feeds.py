#!/usr/bin/env python3
"""Check every configured feed from THIS machine and report what actually works.

Feed URLs move. This script fetches each one (honouring robots.txt), reports the
status, and can write the results back into data/sources.json so a broken feed is
switched off rather than retried forever.

    python -m scripts.verify_feeds            # report only
    python -m scripts.verify_feeds --write    # also disable feeds that failed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion import google_news  # noqa: E402
from app.ingestion.fetcher import FeedFetcher  # noqa: E402
from app.ingestion.registry import SOURCES_FILE, load_sources_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true",
                        help="disable sources whose feed did not work")
    args = parser.parse_args()

    payload = load_sources_file()
    results: list[tuple[str, str, str]] = []

    with FeedFetcher() as fetcher:
        # Google News discovery feeds are built, not stored.
        for slug, url in google_news.default_discovery_feeds():
            res = fetcher.fetch(url, source_slug="google-news", source_name="Google News",
                                discovery_channel="google_news")
            status = "OK" if res.ok and res.count else ("SKIP" if res.skipped_reason else "FAIL")
            results.append((f"google-news:{slug}", status,
                            res.skipped_reason or res.error or f"{res.count} items"))

        for source in payload["sources"]:
            if not source.get("feed_url"):
                results.append((source["slug"], "NONE", source.get("notes", "no feed configured")))
                continue
            res = fetcher.fetch(
                source["feed_url"], source_slug=source["slug"], source_name=source["name"]
            )
            if res.ok and res.count:
                status, detail = "OK", f"{res.count} items"
                source["feed_verified"] = True
            elif res.ok:
                status, detail = "EMPTY", res.skipped_reason or "feed parsed but had no items"
            elif res.skipped_reason:
                status, detail = "SKIP", res.skipped_reason
            else:
                status, detail = "FAIL", res.error or "unknown error"
                if args.write:
                    source["enabled"] = False
            results.append((source["slug"], status, detail))

    width = max(len(r[0]) for r in results) + 2
    for slug, status, detail in results:
        print(f"{slug.ljust(width)}{status.ljust(7)}{detail}")

    if args.write:
        SOURCES_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
        print(f"\nwrote {SOURCES_FILE}")

    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"\n{len(results)} feeds checked, {failed} failed")
    return 1 if failed and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
