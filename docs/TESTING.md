# Testing

## Backend

```bash
cd backend
createdb briefly_test
export BRIEFLY_TEST_DATABASE_URL=postgresql+psycopg://briefly:briefly@localhost:5432/briefly_test

pip install -e ".[dev]"
pytest -q
```

177 tests. Integration tests run against a real PostgreSQL database — the
pipeline depends on JSONB and on the `summary_word_count <= 30` check
constraint, so testing against SQLite would be testing something other than what
ships. Tests that need a database skip cleanly when it is not there.

```bash
pytest tests/test_wordcount.py -v            # the 30-word rule
pytest tests/test_similarity_clustering.py   # clustering
pytest tests/test_facts_and_summary.py       # extraction and grounding
pytest tests/test_qc_ranking_diversity.py    # quality gates
pytest tests/test_ingestion.py               # feeds and compliance
pytest tests/test_pipeline_integration.py    # end to end
pytest tests/test_podcast.py                 # narration and audio
pytest tests/test_api.py                     # the contract the app codes against
pytest --cov=app --cov-report=term-missing   # coverage
ruff check app scripts tests                 # lint
```

### What the suite actually asserts

Not "the function returns something" — the properties that matter:

* **The 30-word rule holds** under every path: clause assembly, trimming, any
  limit, idempotently, and the database itself rejects an over-length row.
* **Ten reports of one event become one story** with one source row per
  publisher and no duplicates, while "Delhi Metro fares to rise" and "Mumbai
  Metro fares to rise" stay apart despite sharing almost every word.
* **Invented facts are rejected**: a wrong figure, a name not in the sources, a
  fabricated claim, an unsupported evidence span, an attribution to someone
  never mentioned — each has its own test.
* **The brief's own example works**: "The government lied about the economic
  figures" is blocked as an unattributed allegation; "The opposition disputed
  the government's economic figures, while officials defended the published
  data" passes clean.
* **Ranking contains no engagement signal** — asserted directly against the
  weights table, so adding one would fail the build.
* **A flagged story never publishes**, and a flagged episode is never voiced.
* **The podcast reads the shared story database** — episode entries must be a
  subset of published stories, and each segment's narration must differ from the
  card summary it came from.
* **No credential ever appears in an API response.**

### Exercising the whole thing offline

```bash
python -m scripts.load_sample_feeds --reset --podcast
```

Runs the fictional sample feeds through the real ingestion, clustering,
extraction, summarisation, ranking, quality-control and podcast code — only the
HTTP fetch is swapped for reading a file. Expect 6 stories from 18 articles and
two episodes with real audio in `backend/var/media/`.

Everything in `backend/tests/fixtures/feeds/` is invented. The outlet names are
routing labels; the headlines, people, places and figures describe no real
event.

## iOS

```bash
cd ios
xcodebuild test -scheme Briefly -destination 'platform=iOS Simulator,name=iPhone 15'
```

Or ⌘U in Xcode.

The XCTest suite covers: decoding the bundled snapshot (a real contract test
against the API's own serialisers), the 30-word cap holding in the shipped data,
every source carrying a name, headline and link, the diversity disclaimer always
being present, date parsing at both precisions, repository pagination, the
fallback path reporting itself honestly, an unauthorised key *not* being masked
by sample data, bookmark persistence and corruption recovery, and feed
navigation.

### Static checks without a Mac

```bash
python3 tools/check_ios_project.py
```

A compiler is the right tool for checking Swift; this is what to use when you do
not have one to hand. It verifies balanced delimiters, duplicate declarations,
members accessed on Briefly's own types actually existing, every `View` having a
body, `@Environment` objects being injected somewhere, bundled resources the
code loads being present, named colours existing in the asset catalogue, no
credential patterns anywhere in the app target, `Info.plist` declaring
background audio, and the Xcode project referencing no undefined objects.

It found real bugs during development. To confirm it still bites, break
something on purpose:

```bash
sed -i 's/BrieflyColor.inkFaint/BrieflyColor.typo/' \
  ios/Briefly/Features/Shared/StateViews.swift
python3 tools/check_ios_project.py    # FAIL  BrieflyColor.typo does not exist
git checkout ios/Briefly/Features/Shared/StateViews.swift
```

## Keeping the app and the API in step

```bash
cd backend
python -m scripts.export_mock_data
```

Regenerates `ios/Briefly/Resources/*.json` from the live serialisers, and
re-encodes the latest generated episodes into `sample-daily.mp3` and
`sample-deep-dive.mp3` so the bundled podcast tab plays offline. If a field is
renamed on the server, the iOS decoding tests fail on the next run — which is
the point of generating the snapshot rather than hand-writing it.

## Continuous integration

```yaml
name: briefly
on: [push, pull_request]

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: briefly
          POSTGRES_PASSWORD: briefly
          POSTGRES_DB: briefly_test
        options: >-
          --health-cmd pg_isready --health-interval 5s
          --health-timeout 5s --health-retries 10
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: sudo apt-get update && sudo apt-get install -y espeak-ng ffmpeg
      - run: pip install -e "./backend[dev]"
      - run: ruff check backend/app backend/scripts backend/tests
      - run: pytest -q
        working-directory: backend
        env:
          BRIEFLY_TEST_DATABASE_URL: postgresql+psycopg://briefly:briefly@localhost:5432/briefly_test
      - run: python3 tools/check_ios_project.py

  ios:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
      - run: |
          xcodebuild test -scheme Briefly \
            -destination 'platform=iOS Simulator,name=iPhone 15'
        working-directory: ios
```
