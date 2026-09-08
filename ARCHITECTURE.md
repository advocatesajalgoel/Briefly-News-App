# Architecture

## The shape of the thing

Briefly is one pipeline with two renderings. Articles come in from feeds, get
clustered into events, get reduced to structured facts, and are stored once.
The 30-word card and the audio briefing are both written *from those fact rows*
— neither reads article prose, and neither can say anything the other could not.

That constraint is the whole design. It is why the podcast cannot contradict the
cards, why a correction propagates to both, and why "did Briefly make this up?"
is a question with a mechanical answer.

## Backend modules

| Module | Responsibility |
|---|---|
| `app/config.py` | All configuration from the environment. `respect_robots` is pinned on. |
| `app/models.py` | SQLAlchemy models — the shared story database |
| `app/enums.py` | Processing status, source kind and access, fact kinds |
| `app/text/wordcount.py` | The 30-word rule: `WordBudget`, clause assembly, trimming |
| `app/text/normalize.py` | Cleaning, URL canonicalisation, entity/number/date extraction |
| `app/text/similarity.py` | TF-IDF, cosine, entity matching, n-gram overlap |
| `app/text/style_guard.py` | Sensational, opinionated and unattributed language |
| `app/text/gazetteer.py` | Place names, used to keep lookalike events apart |
| `app/ingestion/` | Feed fetching, robots gate, parsing, publisher crediting |
| `app/llm/` | Extraction backends: `rule_based`, `anthropic`, `openai` |
| `app/pipeline/clustering.py` | Many reports of one event → one story |
| `app/pipeline/facts.py` | Grounding verification — the anti-hallucination gate |
| `app/pipeline/summarize.py` | Clause dedupe, glue, word budget, style re-check |
| `app/pipeline/diversity.py` | The Source Diversity indicator |
| `app/pipeline/ranking.py` | Ranking. No engagement signal exists in it. |
| `app/pipeline/qc.py` | Ten gates. Failing means flagged, never silently dropped. |
| `app/pipeline/orchestrator.py` | The stages, chained, with an audit row per run |
| `app/podcast/` | Story briefs, narration, episode assembly, persistence |
| `app/tts/` | Pluggable speech: `local`, `elevenlabs`, `openai`, `azure` |
| `app/storage/` | Audio storage: local filesystem or S3-compatible |
| `app/api/` | FastAPI routers: stories, podcast, bookmarks, admin, health |
| `app/jobs/` | APScheduler wiring and the standalone worker process |

## Data model

```
Category ──< Story >── StorySource >── Source
                │  │                     │
                │  └──< ExtractedFact    └──< Article
                │
                ├──< Bookmark >── User
                └──< PodcastStory >── PodcastEpisode
```

* **Article** — one item as it appeared in one publisher's feed. Their headline,
  the short blurb they chose to syndicate, the canonical URL. Never a scraped body.
* **Story** — a cluster of articles about one event. Carries the neutral
  headline, the ≤30-word summary, counts, diversity, rank and QC report.
* **StorySource** — the transparency row. One per (story, publisher), holding
  their own headline, publication time and link.
* **ExtractedFact** — a structured fact with its slot, kind, attribution, the
  verbatim evidence that supports it, and how many independent sources carry it.
* **PodcastEpisode / PodcastStory** — the episode, its script segments, and
  which story each segment narrates with its offset in the audio.
* **PipelineRun** — an audit trail of automated runs.

Two constraints in the schema are load-bearing:

```sql
CHECK (summary_word_count <= 30)                    -- the 30-word rule
UNIQUE (story_id, source_id)                        -- one row per publisher
```

## Clustering, in detail

Cheap signals first:

1. **Time window.** Reports more than ~30 hours apart are follow-ups, not the
   same event.
2. **Candidate generation.** An inverted index over tokens, so only plausible
   pairs are scored.
3. **Composite similarity.** Lexical TF-IDF cosine (0.55), named-entity
   containment (0.30), shared numbers (0.15). Entity matching handles the three
   forms news copy actually uses: exact, containment ("Reserve Bank" /
   "Reserve Bank of India") and initialism ("RBI").
4. **City guard.** Two reports set in *different named cities* are never merged,
   however similar the wording. This is what keeps "Delhi Metro fares to rise"
   apart from "Mumbai Metro fares to rise", which share almost every word.
   Only cities are compared — one outlet writing "India" while another writes
   "New Delhi" is the same event, so countries and regions are excluded.
5. **Single-link agglomeration** over the composite score.
6. **Evidence merge.** A second pass joins clusters that share several
   *distinctive* terms — ones only a handful of documents in the batch use.
   Publishers describe the same event in very different words ("the central
   bank", "the monetary committee", "Ordelia") which keeps plain similarity
   below any globally safe threshold, but they do quote the same rare names and
   the same figures. Requiring several rare shared terms is far more precise
   than simply lowering the threshold, because unrelated stories in a section
   share *common* vocabulary, not rare vocabulary.

A note on what was tried and rejected: an asymmetric containment measure was
added first, on the theory that a short wire snap should match a long write-up.
On L2-normalised vectors it reduces to cosine algebraically, and on raw weights
it saturates at 1.0 for any short document whose words all appear in a long one.
It was removed rather than kept as a misleading no-op; `lexical_similarity`
documents this.

`EmbeddingProvider` is the seam for a vector model. Nothing else changes when
one is added — `pair_similarity` already takes the maximum of the lexical and
embedding scores.

## Fact extraction and grounding

The `rule_based` backend is a real extractor, not a stub. It segments the
headline and blurb and fills slots using linguistic cues: attribution verbs and
"according to" for speakers, dispute and hedging vocabulary for kind, a
gazetteer for places, regexes for figures and dates. Every fact keeps the
verbatim span it came from.

Nothing is marked `confirmed` at that stage. That happens only when several
*independent* publishers, or an official source, carry the same fact.

Then `verify_grounding` runs, and it runs identically whichever backend
produced the facts. This is the point: swapping in a hosted model cannot widen
what Briefly is allowed to assert.

## Ranking

Weights sum to 1.0 and live in one constant so a change is visible in a diff:

| Component | Weight | Why |
|---|---|---|
| Recency | 0.26 | 9-hour half-life |
| Independent sources | 0.24 | Log scale — the 2nd source matters far more than the 9th |
| Diversity | 0.14 | High / medium / low |
| Primary source | 0.12 | An official statement is on the record |
| Geographic relevance | 0.10 | How much of the sourcing is local to the reader |
| Topic relevance | 0.08 | Section preferences |
| Substance | 0.06 | Rewards checkable specifics over vibes |

A single-source story is capped at 0.55 — it is a lead, not a confirmed story,
and must not outrank a well-corroborated one on freshness alone. A test asserts
that no engagement signal (clicks, dwell, shares) exists in the weights.

## Podcast

`Briefly Daily` targets 5–10 minutes and fills that window by **adding stories,
never by padding**. If the sources do not support the target, the episode is
shorter and quality control records a warning. `Deep Dive` targets 10–20 minutes
on the best-covered story and says out loud when the reporting was too thin.

The narrator's own framing vocabulary is declared in
`app/podcast/narrator.py::FRAMING_VOCABULARY` and excluded from the grounding
check — otherwise the show's own voice ("here is what is confirmed") would read
as unsourced assertion. Counts Briefly derives from its own data ("four
independent outlets") are allowed explicitly for the same reason.

## The web app

`site/index.html` is a second client for the same data — one file, no build
step, no framework, no third-party request of any kind. It exists because the
native app cannot be installed on a phone without Apple's signing chain, and an
app nobody can install is not finished.

It is deliberately not a port of the SwiftUI code. It reimplements the same
decisions in the medium's own terms:

* one story per viewport, `scroll-snap-type: y mandatory` where SwiftUI uses
  `scrollTargetBehavior(.paging)`;
* the same source sheet, diversity pips and disclaimer text, read from the same
  JSON fields, so the two clients cannot drift apart in what they claim;
* `localStorage` for bookmarks, matching the native app's local-only rule —
  nothing about what you read leaves the phone;
* a service worker with two policies: network-first for `api/`, because a news
  app must never quietly prefer a stale story, and cache-first for the shell and
  audio, with the audio cache capped at two episodes so a briefing produced
  twice a day cannot fill a phone.

The typography uses `ui-serif` and `-apple-system` rather than a webfont. On
iOS those resolve to New York and SF Pro, which is both better than what a font
CDN would send and one fewer party that learns when you open the news.

## iOS app

| Layer | Files |
|---|---|
| Design system | `BrieflyColors`, `BrieflyTypography`, `BrieflyLayout` |
| Models | `Story`, `NewsCategory`, `PodcastEpisode`, `Formatting` |
| Networking | `APIClient`, `APIConfiguration`, `NewsRepository` (+ bundled and fallback) |
| Feed | `FeedView`, `FeedViewModel`, `StoryCardView`, `SourcesSheet` |
| Podcast | `AudioPlayerController`, `PlayerViews`, `PodcastView`, `PodcastViewModel` |
| Saved / Settings | `SavedView`, `SettingsView`, `AboutView` |
| Support | `BookmarkStore`, `AppSettings`, `Haptics`, `DeviceIdentifier` |

Notable decisions:

* **Paging with SwiftUI's own scroll targets** (`scrollTargetBehavior(.paging)`
  + `containerRelativeFrame(.vertical)`) rather than a rotated `TabView`. It
  gives a real swipe-up/swipe-down page turn, keeps VoiceOver's reading order
  correct, and lets a card scroll internally when text is set very large.
* **No images on cards.** Briefly has no licence to publisher photography.
  Text-only also makes the card load instantly and read cleanly at every
  Dynamic Type size.
* **Serif headlines, sans body.** The pairing is what makes a card read as an
  edited page rather than a feed item, and it is the most recognisable part of
  the identity.
* **Three repositories.** `RemoteNewsRepository` talks to a server;
  `BundledNewsRepository` reads the snapshot; `FallbackNewsRepository` tries the
  first and falls back to the second — *and tells the reader it did*. A rejected
  API key is deliberately **not** masked by sample data; it surfaces as an error.
* **Bookmarks store the whole story**, so a saved card opens with its sources
  and links on a plane.
* The bundled snapshot is generated by `backend/scripts/export_mock_data.py`
  from the real serialisers, so the Swift models are tested against the shapes
  the server actually returns.
