# API reference

Base URL: whatever you deploy to. Interactive docs are served at `/docs`, and
the machine-readable schema at `/openapi.json`.

Two surfaces:

* **Read API** (`/v1/...`) — what the iPhone app uses. Serves already-public
  headlines and links, so it is open by default. Set `BRIEFLY_CLIENT_API_KEY` to
  require an `X-Briefly-Key` header.
* **Admin API** (`/v1/admin/...`) — always requires `X-Admin-Token`. Returns
  `503` if `BRIEFLY_ADMIN_TOKEN` is unset, so it cannot be accidentally left
  open.

All timestamps are ISO-8601 UTC. Field names are `snake_case`; the Swift client
converts them.

---

## Health

### `GET /v1/health` (also `GET /health`)

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "production",
  "database": "ok",
  "llm_provider": "rule_based",
  "tts_provider": "local",
  "storage_backend": "local",
  "scheduler_enabled": true,
  "published_stories": 42,
  "latest_story_at": "2026-09-06T05:12:44Z",
  "latest_episode_at": "2026-09-06T00:31:02Z"
}
```

`latest_story_at` is the field to alert on: if it stops moving, ingestion has
stopped.

---

## Stories

### `GET /v1/categories`

```json
[
  {"id": "…", "slug": "for-you", "name": "For You", "description": "A ranked mix across every section.",
   "sort_order": 10, "is_synthetic": true},
  {"id": "…", "slug": "india", "name": "India", "sort_order": 20, "is_synthetic": false}
]
```

### `GET /v1/stories`

| Parameter | Default | Notes |
|---|---|---|
| `category` | — | Slug. Omit, or use `for-you` / `all`, for the ranked mix. |
| `limit` | 20 | 1–50 |
| `cursor` | — | From the previous page's `next_cursor` |

Ordered by `rank_score` descending, with the id as a tiebreak so the swipe stack
never reshuffles under the reader's thumb. A malformed cursor returns `400`; an
unknown category returns `404`.

```json
{
  "items": [{
    "id": "a7714f5b-b062-4a04-8f4d-b2bba5feceab",
    "slug": "20260906-benchmark-rate-unchanged-…",
    "headline": "Benchmark rate unchanged at 6.25 per cent, committee splits five to one",
    "summary": "Benchmark rate remains at 6.25 per cent, the monetary committee said, on Friday.",
    "summary_word_count": 13,
    "dek": "…",
    "category_slug": "business",
    "category_name": "Business",
    "published_at": "2026-09-06T06:22:55.886238Z",
    "first_reported_at": "2026-09-05T07:50:00Z",
    "last_reported_at": "2026-09-05T09:00:00Z",
    "source_count": 5,
    "independent_source_count": 5,
    "has_official_source": true,
    "has_disputed_claims": false,
    "confidence": "confirmed",
    "diversity": {
      "level": "high",
      "total": 5, "independent": 5, "countries": 2, "has_official": true,
      "lines": ["4 Indian sources", "1 international source", "1 official source"],
      "by_kind": {"national": 3, "international": 1, "official": 1},
      "by_country": {"IN": 4, "GB": 1},
      "disclaimer": "Source diversity counts where reporting came from. It is not a measurement of bias."
    },
    "sources": [{
      "source_name": "Press Information Bureau (Government of India)",
      "source_kind": "official",
      "original_headline": "Monetary committee announces rate decision",
      "original_url": "https://…",
      "published_at": "2026-09-05T08:05:00Z",
      "is_primary_source": true
    }],
    "facts": [
      {"slot": "what", "kind": "confirmed", "text": "…", "attributed_to": null, "support_count": 5},
      {"slot": "number", "kind": "number", "text": "6.25 per cent", "attributed_to": null, "support_count": 5}
    ],
    "rank_score": 0.721
  }],
  "next_cursor": "eyJyYW5rIjogMC40OTgzMzMsICJpZCI6ICJjYWZi…",
  "total_estimate": 42
}
```

`confidence` is one of `confirmed`, `disputed`, `reported`.
`facts[].kind` is one of `confirmed`, `attributed`, `disputed`, `uncertain`,
`number`, `date`.

The `disclaimer` travels with the diversity object on purpose: a client cannot
render the level without it.

### `GET /v1/stories/{story_id}`
### `GET /v1/stories/by-slug/{slug}`

A single story. `404` if it is not published — unpublished and flagged stories
are never served to readers.

### `POST /v1/stories/batch`

Body: a JSON array of up to 100 story ids. Returns the published ones, in the
order requested. Used to refresh locally-saved bookmarks in one round trip.

---

## Podcast

### `GET /v1/podcast/episodes`

| Parameter | Default | Notes |
|---|---|---|
| `kind` | — | `daily` or `deep_dive` |
| `limit` | 20 | 1–50 |
| `offset` | 0 | |

### `GET /v1/podcast/latest?kind=daily`

The newest published episode of that kind, **including the transcript**.
`404` when none has been produced yet.

```json
{
  "id": "…",
  "kind": "daily",
  "slug": "daily-20260906-briefly-daily-06-september-2026",
  "title": "Briefly Daily — 06 September 2026",
  "subtitle": "6 stories, with their sources named.",
  "edition_date": "2026-09-06T06:22:55.935485Z",
  "published_at": "2026-09-06T06:22:57.927483Z",
  "audio_url": "https://…/media/episodes/2026/09/daily-20260906-….mp3",
  "audio_mime_type": "audio/mpeg",
  "audio_duration_seconds": 222,
  "audio_bytes": 3045086,
  "estimated_duration_seconds": 226,
  "script_word_count": 566,
  "segments": [
    {"kind": "intro", "title": "Introduction", "story_id": null,
     "word_count": 47, "start_offset_seconds": 0},
    {"kind": "story", "title": "1. Cyclone Verath makes landfall…",
     "story_id": "…", "word_count": 86, "start_offset_seconds": 18}
  ],
  "story_ids": ["…"],
  "transcript": "Good morning. This is Briefly Daily for…"
}
```

`segments` are the chapters the player jumps between. Offsets are re-timed
against the audio actually produced, not the estimate.

### `GET /v1/podcast/episodes/{episode_id}`

---

## Bookmarks (optional sync)

v1 of the app stores bookmarks on the device. These endpoints exist so the same
list can follow a reader to a second device later without a schema change.

```
GET    /v1/bookmarks?device_id=…          → [Story]
POST   /v1/bookmarks                      → 201, idempotent
       {"device_id": "…", "story_id": "…", "note": null}
DELETE /v1/bookmarks/{story_id}?device_id=…  → 204
```

`device_id` is a random value the app generates and keeps in the keychain. It is
not the advertising identifier and not the vendor identifier.

---

## Admin

Every route requires `X-Admin-Token`.

| Route | What it does |
|---|---|
| `POST /v1/admin/seed` | Load `data/categories.json` and `data/sources.json` |
| `POST /v1/admin/pipeline/ingest` | Fetch feeds |
| `POST /v1/admin/pipeline/cluster` | Cluster pending articles |
| `POST /v1/admin/pipeline/process` | Extract, summarise, rank, gate |
| `POST /v1/admin/pipeline/run?skip_ingest=false` | All of the above, audited |
| `POST /v1/admin/podcast/daily?voice=true` | Build and optionally voice Briefly Daily |
| `POST /v1/admin/podcast/deep-dive?story_id=…&voice=true` | Build a Deep Dive |
| `GET /v1/admin/stories/flagged` | The review queue, with QC reports |
| `POST /v1/admin/stories/{id}/publish` | Human override after review |
| `POST /v1/admin/stories/{id}/archive` | Take a story down |
| `GET /v1/admin/sources` | Source health: last fetch, last error, failure count |
| `POST /v1/admin/sources/{slug}/toggle?enabled=false` | Enable or disable a source |
| `GET /v1/admin/stats` | Counts by status |

A pipeline run returns per-stage statistics:

```json
{
  "ingest":     {"feeds_ok": 11, "articles_created": 18, "articles_duplicate": 3, "errors": []},
  "clustering": {"stage": "clustering", "processed": 18, "created": 6},
  "processing": {"stage": "processing", "processed": 6, "published": 6, "flagged": 0}
}
```

---

## Errors

| Status | Meaning |
|---|---|
| `400` | Malformed cursor |
| `401` | Bad or missing `X-Admin-Token` / `X-Briefly-Key` |
| `404` | Not found, or not published |
| `409` | Nothing to build (no published stories to narrate) |
| `422` | Validation failure — the body explains which field |
| `503` | Admin endpoints called while `BRIEFLY_ADMIN_TOKEN` is unset |

The client maps these to `APIError` and, for the retryable ones, falls back to
its bundled snapshot — while telling the reader it has done so.
