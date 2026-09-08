# Briefly

A concise, transparent news app for iPhone, and the backend that feeds it.

One story at a time. A neutral headline, a summary of **at most 30 words**, and —
one tap away — every publisher that reported it, what each of them said, when,
and a link to the original. The same story database also produces an audio
briefing, so the podcast and the cards can never disagree with each other.

Briefly does not claim to be unbiased. Choosing what to carry and how to word it
is editing, and editing has a point of view. What Briefly does is **show its
work**: maximum transparency, minimum editorial distortion.

---

## Put it on your iPhone without a Mac

> **New here?** Read [START_HERE.md](START_HERE.md) instead of this section —
> same steps, written for somebody who has never used GitHub.

There are two builds of the same app in here, from the same story database.

**`ios/`** is the native SwiftUI app. Installing it on a phone needs Xcode
signing, so it needs either a Mac or an Apple Developer account —
[docs/BUILDING_WITHOUT_A_MAC.md](docs/BUILDING_WITHOUT_A_MAC.md) covers the
cloud-Mac routes.

**`site/`** is the same app as a web app, and it installs on an iPhone from
Safari with no Mac, no Apple ID and no money. It is not a wrapper around a
website: it is one self-contained page with no third-party requests at all —
no font CDN, no analytics, no tracker — that keeps working offline and appears
on the home screen with its own icon, full screen, no browser chrome.

Nothing is deployed and nothing is rented. A GitHub Action runs the whole
pipeline on a free Linux runner, publishes the result as static JSON and audio,
and GitHub Pages serves it:

```
GitHub Actions (free)          GitHub Pages (free)        your iPhone
──────────────────────         ───────────────────        ───────────
ingest real feeds
cluster into stories
extract and verify facts   ──►  api/stories.json     ──►  Add to Home Screen
summarise in ≤ 30 words         api/episodes.json         works offline
quality-check                   media/*.mp3               no account, no key
narrate and voice
```

**What to do, in order:**

1. Create a free account at [github.com](https://github.com) if you have none.
2. Make a new **public** repository called `briefly`.
3. Upload this folder to it — the web page has an "uploading an existing file"
   link, or run `./push_to_github.sh https://github.com/YOU/briefly.git`.
4. Open the **Actions** tab, choose **Publish site**, press **Run workflow**.
   It takes five to ten minutes. It switches GitHub Pages on by itself; if your
   account blocks that, set *Settings → Pages → Source: GitHub Actions* by hand
   and run it again.
5. When it finishes, the run's summary page prints the address —
   `https://YOU.github.io/briefly/`.
6. Open that address **in Safari on your iPhone**. Tap the Share button, scroll
   down, tap **Add to Home Screen**.

From then on it refreshes itself twice a day, at 06:00 and 18:00 India time.
Tapping the icon opens Briefly, not a browser.

Two honest limits: this is a home-screen web app, not an App Store one — it
cannot send push notifications on iOS unless you allow them, and it will not
appear in the App Store. And a GitHub repository with no activity for 60 days
has its schedules paused; pressing *Run workflow* once resumes them.

---

## What is in this repository

```
briefly/
├── ios/                  SwiftUI iPhone app (Xcode project included)
│   ├── Briefly.xcodeproj
│   ├── Briefly/          32 Swift files — feed, sources, podcast, saved, settings
│   ├── BrieflyTests/     XCTest suite
│   └── project.yml       XcodeGen spec, if you would rather regenerate the project
├── backend/              FastAPI + PostgreSQL pipeline and API
│   ├── app/              ingestion → clustering → facts → summary → ranking → QC → podcast
│   ├── alembic/          database migrations
│   ├── data/             source and category registry (JSON, editable without code changes)
│   ├── scripts/          seeding, feed verification, pipeline CLI, sample loader
│   └── tests/            180 tests
├── site/                 the same app as a web app — installs on iPhone with no Mac
│   ├── index.html        one file: cards, sources, podcast, saved, dark mode
│   ├── sw.js             offline service worker
│   └── manifest.webmanifest
├── docs/                 architecture, deployment, testing, editorial policy
├── tools/                static checker, and the single-file bundler
├── .github/workflows/    free CI: Linux checks, cloud-Mac iOS build, publish the web app
└── codemagic.yaml        alternative free macOS build machine
```

---

## Quick start

### 0. The web app, locally

```bash
cd backend && python -m scripts.load_sample_feeds --reset --podcast
python -m scripts.export_static_site          # writes ../site/api and ../site/media
cd ../site && python3 -m http.server 8899     # http://localhost:8899
```

`site/api/` and `site/media/` are generated, and deliberately not in git — the
publishing workflow builds them fresh and uploads them straight to Pages, so
twice-daily audio never accumulates in the repository's history.

### 1. The app on its own (no backend needed)

```bash
open ios/Briefly.xcodeproj      # with Xcode
# select an iPhone simulator, ⌘R
```

**No Mac?** Push to a public GitHub repo and the included workflow builds and
tests the app on a free cloud Mac, then hands you a simulator build you can run
in a browser. See [docs/BUILDING_WITHOUT_A_MAC.md](docs/BUILDING_WITHOUT_A_MAC.md).
The model layer also compiles and tests on plain Linux:

```bash
cd ios && swift test
```

The app ships with a snapshot of real API responses in `ios/Briefly/Resources/`,
so every screen works immediately — feed, swipe, sources, diversity, sections,
bookmarks, podcast list. Two generated episodes are bundled as audio, so the
player genuinely plays. A banner says **"Sample stories"** the whole time it is
serving them, because presenting sample data as today's news would defeat the
point of the app.

### 2. The backend

```bash
cd backend
cp .env.example .env
# set BRIEFLY_ADMIN_TOKEN — python -c "import secrets;print(secrets.token_urlsafe(32))"

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

createdb briefly                       # or use docker compose (below)
alembic upgrade head
python -m scripts.seed_reference_data

# Bring it to life without touching the network, using the fictional sample feeds:
python -m scripts.load_sample_feeds --reset --podcast

uvicorn app.main:app --reload
# http://localhost:8000/docs
```

Or with Docker:

```bash
cd backend
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
docker compose exec api python -m scripts.seed_reference_data
```

### 3. Point the app at it

In the app: **Settings → Briefly server → `http://localhost:8000` → Save**.
The sample banner disappears and the feed is live.

### 4. Real news

```bash
cd backend
python -m scripts.verify_feeds          # check which feeds work from your network
python -m scripts.verify_feeds --write  # switch off the ones that do not
python -m scripts.run_pipeline all      # ingest → cluster → extract → summarise → QC
python -m scripts.run_pipeline daily-podcast
```

Then set `BRIEFLY_SCHEDULER_ENABLED=true` and run the worker, and it keeps
itself up to date. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## How it works

```
                    Google News RSS  +  publisher feeds  +  official sources
                                          │
                                          ▼
                                  ARTICLE INGESTION
                        robots.txt honoured · conditional GET · no scraping
                                          │
                                          ▼
                                  STORY CLUSTERING
                    TF-IDF + entity matching + shared distinctive terms
                        10 reports of one event → 1 story, 10 sources
                                          │
                                          ▼
                                  FACT EXTRACTION
                   who · what · when · where · why · numbers · dates
              confirmed · attributed · disputed · uncertain — each with evidence
                                          │
                                          ▼
                             GROUNDING VERIFICATION
              a fact that cannot be traced to the sources is discarded
                                          │
                                          ▼
                             SHARED STORY DATABASE
                                          │
                        ┌─────────────────┴─────────────────┐
                        ▼                                   ▼
                  NEWS CARD                            PODCAST
                  ≤ 30 words                     Daily 5–10 min
              assembled from clauses            Deep Dive 10–20 min
              by a word budget, in code        narrated from the same facts
                        │                                   │
                        └─────────────────┬─────────────────┘
                                          ▼
                                  QUALITY CONTROL
        hallucinations · numbers · names · dates · duplicates · repetition
        opinion · attribution · copying · length → pass, or flag for review
```

### The 30-word rule is not a prompt

It is arithmetic, and it is enforced three times:

1. Facts become **ranked clauses**, each with a priority and a required flag.
2. `WordBudget` decides which clauses fit — it drops the least important ones
   rather than truncating a sentence into nonsense.
3. The database refuses the row: `CHECK (summary_word_count <= 30)`.

A regression in a model prompt therefore cannot put a 34-word card on your
phone. The word counter deliberately takes the *stricter* of two readings, so
"cease-fire" costs two words rather than one.

### Nothing is asserted without a source

Every extraction backend — the deterministic one and the hosted models — is put
through the same grounding check. A proposed fact is dropped unless:

* its verbatim evidence span appears in the supplied material,
* every figure in it appears in the sources (rounding 4.6 to 5 fails),
* every capitalised name in it appears in the sources,
* at least 70% of its content words occur in the sources,
* the person it is attributed to is actually mentioned.

### The app holds no secrets

The iPhone app knows one thing about your infrastructure: a public base URL. No
model key, no text-to-speech credential, no storage key, no database password
is present anywhere in the bundle, and a test asserts that none of them appear
in an API response either.

---

## Runs with no external accounts at all

| Layer | Default | Needs a credential? |
|---|---|---|
| Fact extraction and summarisation | `rule_based` — deterministic, offline | **No** |
| Text to speech | `local` — espeak-ng | **No** |
| Audio storage | local filesystem, served at `/media` | **No** |
| News discovery | Google News RSS + publisher feeds | **No** |

Set `BRIEFLY_LLM_PROVIDER=anthropic` (or `openai`) and `BRIEFLY_TTS_PROVIDER=elevenlabs`
(or `openai`, `azure`) to upgrade the prose and the voice. Each provider falls
back to the offline one when its key is missing, so a missing credential
degrades quality — never availability.

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Every module, the data model, and why each decision was made |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Running it for real: server, database, scheduler, storage, TLS |
| [docs/TESTING.md](docs/TESTING.md) | How to run and extend both test suites |
| [docs/BUILDING_WITHOUT_A_MAC.md](docs/BUILDING_WITHOUT_A_MAC.md) | Getting it onto an iPhone with no Mac — the web app route, and the cloud-Mac ones |
| [docs/EDITORIAL_POLICY.md](docs/EDITORIAL_POLICY.md) | The rules the pipeline enforces, and their limits |
| [docs/API.md](docs/API.md) | Endpoint reference |

---

## Legal and ethical position

* Only feed material a publisher chose to syndicate is ingested. No article
  scraping, no paywall circumvention, no authentication, no ignoring
  `robots.txt` — that last one is pinned on in code and cannot be configured off.
* Publishers' own headlines are shown verbatim and credited; Briefly's own
  summary is checked for excessive overlap with any single source and rejected
  if it leans too close.
* Outlets that require a commercial licence (Reuters, AP, PTI) ship **disabled**
  rather than guessed at. They appear only when an aggregator credits them, with
  a link and no stored summary.
* The Source Diversity indicator is a count of where reporting came from. It is
  not a bias score, and the disclaimer travels with the data so the UI cannot
  display the number without it.
* Briefly is an independent implementation. It is not affiliated with, and
  copies no code, design, branding or assets from, any existing news app.
