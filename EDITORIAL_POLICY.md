# Editorial policy

**Maximum transparency. Minimum editorial distortion.**

Briefly does not claim to be unbiased, and this document is not a claim to be.
Deciding which stories to carry, which formulation of a headline to keep and
which fact goes in thirty words is editing, and editing has a point of view.
What Briefly can honestly promise is that its working is visible and that a
short list of things are mechanically impossible.

## What is enforced in code

These are not guidelines. Each is a check that runs before anything publishes,
and failing one flags the item for review instead of shipping it.

### Nothing is asserted without a source

Every proposed fact must survive `verify_grounding`:

| Check | What it catches |
|---|---|
| Evidence span present in the material | A claim with no traceable origin |
| Every figure appears in the sources | A model rounding 4.6 to 5 |
| Every capitalised name appears in the sources | An invented or substituted person |
| ≥70% of content words occur in the sources | A fabricated clause hung on real names |
| The attributed speaker is mentioned | A quote put in someone's mouth |

This runs identically whichever backend produced the facts. Switching from the
deterministic extractor to a hosted model cannot widen what Briefly may assert.

### Thirty words, arithmetically

Facts become ranked clauses; a word budget decides which fit; the database
refuses the row if the count exceeds thirty. A prompt regression cannot put a
34-word card on a phone. The counter takes the stricter of two readings, so
"cease-fire" costs two words rather than one.

### Allegations stay allegations

Wrongdoing described without naming who alleges it is a **blocker**.

> Blocked: *The government lied about the economic figures.*
>
> Published: *The opposition disputed the government's economic figures, while
> officials defended the published data.*

Facts carry a `kind`: `confirmed`, `attributed`, `disputed`, `uncertain`.
Nothing is promoted to `confirmed` by the extractor — that happens only when
several independent publishers, or an official source, state it directly.

### Loaded language is rejected

Sensational vocabulary ("slammed", "shocking", "bombshell"), opinion markers
("clearly", "obviously", "unfortunately"), exclamation marks and shouting caps
are blockers in Briefly's own copy.

The list is deliberately conservative about ordinary words. "Disaster" and
"storm" are not on it: they are plain descriptions in weather and civil-defence
reporting, and flagging them would teach the pipeline to avoid the correct word.
A publisher's own headline is never rewritten — it is quoted as they wrote it in
the source list, loaded or not.

### Copying is measured

Briefly's summary is compared against every source with a seven-word shingle
overlap; narration uses eight. Two outlets reporting "the rate remains at 6.25
per cent" will inevitably share five consecutive words, because that is the
fact. A shared run of seven or more is the publisher's sentence, not the fact,
and it is a blocker.

This is why summaries are assembled from clauses drawn from different places and
why attribution is moved to the end of the sentence rather than the front: a
card built out of fragments is genuinely Briefly's own prose, and it measures as
such.

### Ranking is not engagement

The weights are recency, independent sources, diversity, primary-source
availability, geographic relevance, topic relevance and substance. There is no
click signal, no dwell time, no share count — a test asserts their absence.

A single-source story is capped so it can never outrank a well-corroborated one
on freshness alone. It is a lead, not a confirmed story.

## What is enforced by how sources are gathered

* Only what a publisher chose to syndicate: RSS, Atom, documented APIs.
* `robots.txt` is checked before every fetch. Failing to *read* it counts as
  disallowed — if permission cannot be established, Briefly does not fetch.
  The setting that appears to control this is pinned on in code and cannot be
  turned off by configuration.
* `Crawl-delay` is honoured. Conditional GET avoids re-downloading feeds.
* Paywalls, logins and access controls are never worked around. A `401`, `402`
  or `403` is recorded as "access restricted by publisher; not attempting to
  work around it" and the source is left alone.
* Outlets requiring a commercial licence ship disabled rather than guessed at.
* Google News is used for discovery only. It is never listed as a source on a
  card — the publisher it credits is. Briefly does not parse Google News HTML
  and does not decode its redirect tokens.

## The Source Diversity indicator

A count of **where reporting came from**: how many independent newsrooms, how
many kinds of outlet, how many countries, whether a primary source is present.

It is **not** a political-bias score, not a measurement of accuracy, and not a
scientific instrument. The disclaimer is part of the data structure, not a UI
decoration, so a client cannot display the number without it.

Its honest limitation: eight outlets running the same wire copy will score
higher than three outlets that each sent a reporter, because Briefly cannot see
whose copy is whose. The `is_independent` flag on a source is the lever for
that, and it is set by hand.

## What Briefly does not know

Stating the limits is part of the promise.

* **Selection is editorial.** Which feeds are configured determines which
  stories can exist. That choice is yours, and it is a point of view.
* **Feed blurbs are thin.** Extraction works from a headline and a syndicated
  paragraph, not a full article. Facts inside the body are invisible.
* **Clustering is imperfect.** It will occasionally split one event in two, or
  join two related events. Thresholds are tuned to prefer splitting, because a
  wrongly merged story misattributes sources — the worse failure.
* **Entity recognition is capitalisation-based.** It is deliberately
  conservative: a missing entity is better than a wrong one.
* **"Confirmed" means corroborated, not true.** Several outlets can repeat the
  same wrong thing. It records agreement, which is all it can observe.
* **Deep Dives are only as deep as the reporting.** When the material runs out
  the episode ends early and says so rather than padding.

## Corrections

Every story keeps its articles, its facts with evidence spans, and its QC
report. Re-running the pipeline over a cluster replaces its fact set atomically,
so a corrected source produces a corrected card and a corrected briefing
together — they are the same rows.

Flagged items sit in `/v1/admin/stories/flagged` with the reasons attached.
Silence is never the failure mode: nothing fails quietly to publish.
