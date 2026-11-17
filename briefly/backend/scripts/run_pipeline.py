#!/usr/bin/env python3
"""Run pipeline stages by hand.

    python -m scripts.run_pipeline ingest
    python -m scripts.run_pipeline cluster
    python -m scripts.run_pipeline process
    python -m scripts.run_pipeline all
    python -m scripts.run_pipeline daily-podcast
    python -m scripts.run_pipeline deep-dive [--story-id UUID]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import session_scope  # noqa: E402
from app.pipeline import orchestrator  # noqa: E402
from app.podcast import service as podcast_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage",
        choices=["ingest", "cluster", "process", "all", "daily-podcast", "deep-dive"],
    )
    parser.add_argument("--story-id", default=None)
    parser.add_argument("--no-voice", action="store_true", help="skip text-to-speech")
    args = parser.parse_args()

    with session_scope() as db:
        if args.stage == "ingest":
            out = orchestrator.run_ingest(db)
        elif args.stage == "cluster":
            out = orchestrator.run_clustering(db)
        elif args.stage == "process":
            out = orchestrator.run_processing(db)
        elif args.stage == "all":
            out = orchestrator.run_full(db)
        elif args.stage == "daily-podcast":
            episode = podcast_service.generate_daily_episode(db)
            if episode is None:
                out = {"created": False, "reason": "no published stories"}
            else:
                if not args.no_voice and episode.status != "flagged":
                    podcast_service.synthesise_episode(db, episode)
                out = {
                    "slug": episode.slug,
                    "status": episode.status,
                    "stories": len(episode.entries),
                    "words": episode.script_word_count,
                    "estimated_seconds": episode.estimated_duration_seconds,
                    "audio_url": episode.audio_url,
                    "qc_passed": (episode.qc_report or {}).get("passed"),
                }
        else:
            story_id = uuid.UUID(args.story_id) if args.story_id else None
            episode = podcast_service.generate_deep_dive_episode(db, story_id=story_id)
            if episode is None:
                out = {"created": False, "reason": "no suitable story"}
            else:
                if not args.no_voice and episode.status != "flagged":
                    podcast_service.synthesise_episode(db, episode)
                out = {
                    "slug": episode.slug,
                    "status": episode.status,
                    "words": episode.script_word_count,
                    "audio_url": episode.audio_url,
                    "qc_passed": (episode.qc_report or {}).get("passed"),
                }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
