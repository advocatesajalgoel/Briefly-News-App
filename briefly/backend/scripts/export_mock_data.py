#!/usr/bin/env python3
"""Export the current API responses as the JSON the iOS app bundles.

The app ships with a snapshot so it runs, and is fully explorable, before any
backend exists. Generating that snapshot from the real serialisers rather than
hand-writing it means the Swift `Codable` models are checked against the same
shapes the server actually returns.

    python -m scripts.export_mock_data [--out ../ios/Briefly/Resources]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import REPO_ROOT  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "ios" / "Briefly" / "Resources"


def _bundle_audio(episode: dict, out: Path) -> dict:
    """Copy an episode's audio into the app bundle and point the URL at it.

    Without this the sample podcast tab lists episodes that cannot play, because
    their URLs point at a development server the phone cannot reach. Shipping the
    audio makes the offline experience complete, and the app resolves a bare
    filename against its own bundle (see `PodcastEpisode.resolveAudioURL`).

    The copy is re-encoded down to 48 kbps mono — plenty for speech, and it keeps
    the app bundle small.
    """
    from app.config import get_settings
    from app.tts.base import ffmpeg_path

    url = episode.get("audio_url")
    if not url:
        return episode

    settings = get_settings()
    key = url.split("/media/", 1)[-1] if "/media/" in url else None
    source = (settings.media_dir / key) if key else None
    if source is None or not source.exists():
        return episode

    target = out / f"sample-{episode['kind'].replace('_', '-')}.mp3"
    binary = ffmpeg_path()
    if binary:
        proc = subprocess.run(
            [binary, "-y", "-loglevel", "error", "-i", str(source),
             "-codec:a", "libmp3lame", "-b:a", "48k", "-ac", "1", str(target)],
            capture_output=True,
        )
        if proc.returncode != 0:
            shutil.copyfile(source, target)
    else:
        shutil.copyfile(source, target)

    episode = dict(episode)
    episode["audio_url"] = target.name
    episode["audio_bytes"] = target.stat().st_size
    print(f"bundled {target.name} ({target.stat().st_size // 1024} KB)")
    return episode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())

    files: dict[str, object] = {}
    files["mock_categories.json"] = client.get("/v1/categories").json()

    stories = client.get("/v1/stories?limit=50").json()
    files["mock_stories.json"] = stories

    episodes: list[dict] = []
    for kind in ("daily", "deep_dive"):
        response = client.get(f"/v1/podcast/latest?kind={kind}")
        if response.status_code == 200:
            episodes.append(response.json())
    listing = client.get("/v1/podcast/episodes").json()
    by_id = {e["id"]: e for e in episodes}
    for item in listing.get("items", []):
        by_id.setdefault(item["id"], item)

    items = [_bundle_audio(episode, out) for episode in by_id.values()]
    files["mock_episodes.json"] = {"items": items, "next_cursor": None}

    for name, payload in files.items():
        (out / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {out / name}")

    print(
        f"\nstories: {len(stories['items'])}, "
        f"episodes: {len(files['mock_episodes.json']['items'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
