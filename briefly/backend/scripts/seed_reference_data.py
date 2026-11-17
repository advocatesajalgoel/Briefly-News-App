#!/usr/bin/env python3
"""Load categories and sources from backend/data into the database.

    python -m scripts.seed_reference_data
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import session_scope  # noqa: E402
from app.ingestion.registry import sync_categories, sync_sources  # noqa: E402


def main() -> int:
    with session_scope() as db:
        categories = sync_categories(db)
        sources = sync_sources(db)
        print(f"categories: {len(categories)}")
        print(f"sources:    {len(sources)}")
        enabled = [s.slug for s in sources if s.is_enabled]
        print(f"enabled:    {', '.join(enabled)}")
        disabled = [s.slug for s in sources if not s.is_enabled]
        if disabled:
            print(f"disabled:   {', '.join(disabled)}  (need a licence or an unverified feed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
