"""Assign a story to a section.

Order of trust: the aggregator's own topic (it knew which section it served the
item from), then the publisher's feed tags, then the subject of the story, and
only then geography.

Two lessons from real feeds are built in. Subject keywords are not equally
strong: "sensex" settles a story as Business, but "bank" appears in "West Bank"
and "director" in every arrest by the CBI, so a single weak word never decides.
And geography is read from the places a story names — an Indian outlet covering
a court in Brasília has not written an India story because the words "Supreme
Court" appear in it.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlsplit

from app.models import Article, Category
from app.text.gazetteer import foreign_places_in, india_places_in
from app.text.normalize import clean_text

# Words that do mean India but are not places.
INDIA_HINTS = {
    "indian", "lok sabha", "rajya sabha", "rupee", "rbi", "sebi", "isro",
    "niti aayog", "bjp", "congress party", "aap", "tmc", "dmk", "aiadmk",
    "crore", "lakh", "panchayat", "sarpanch", "tehsil", "cbi", "ncb", "nia",
    "aadhaar", "upi", "ipl", "bcci", "modi", "mea",
}

# Keywords that are ordinary words elsewhere. One of these alone decides
# nothing; two, or one alongside a strong keyword, does.
WEAK_KEYWORDS = {
    "bank", "market", "app", "chip", "cloud", "goal", "film", "series", "music",
    "director", "festival", "climate", "profit", "revenue", "tariff", "crude",
    "tournament", "medal", "actor", "actress", "album", "movie", "privacy",
    "silicon", "processor", "algorithm", "researchers", "emissions", "physics",
    "chemistry", "athlete", "streaming", "trailer", "summit", "treaty",
    "president", "railways", "monsoon", "parliament", "supreme court",
    "high court", "state government", "chief minister", "inflation", "software",
    "hockey", "tennis", "satellite", "vaccine", "study published",
}
# Abbreviations that are only places in capitals: "us" is also a pronoun.
_FOREIGN_ABBREVIATION = re.compile(r"(?<![\w.])(?:US|UK|EU|U\.S\.|U\.K\.|UAE|UNSC)(?![\w])")
_FOREIGN_DEMONYMS = {
    "american", "british", "chinese", "russian", "israeli", "iranian",
    "pakistani", "bangladeshi", "sri lankan", "nepali", "nepalese", "french",
    "german", "japanese", "korean", "ukrainian", "palestinian", "saudi",
    "turkish", "afghan", "australian", "canadian", "brazilian", "european",
    "italian", "spanish", "lebanese", "syrian", "iraqi", "egyptian", "mexican",
    "argentine", "indonesian", "malaysian", "thai", "vietnamese", "filipino",
    "south african", "nigerian", "kenyan", "dutch", "swiss", "swedish", "polish",
}
STRONG, WEAK = 2, 1
MIN_SUBJECT_SCORE = 2

# The section a publisher filed the story under, read from its own URL. This
# is the outlet's classification, not a guess at one, so it outranks keywords.
_URL_SECTIONS: dict[str, str] = {
    **dict.fromkeys(("world", "world-news", "international", "global", "us-news",
                     "uk-news", "europe", "americas", "middle-east", "asia-pacific",
                     "africa", "foreign"), "world"),
    **dict.fromkeys(("india", "india-news", "national", "nation", "cities", "city",
                     "states", "state", "elections", "politics", "delhi", "mumbai",
                     "bengaluru", "chennai", "kolkata", "hyderabad", "pune"), "india"),
    **dict.fromkeys(("business", "markets", "economy", "industry", "companies",
                     "money", "finance", "banking", "stocks", "economics",
                     "personal-finance", "wealth"), "business"),
    **dict.fromkeys(("technology", "tech", "gadgets", "science-tech", "internet",
                     "ai", "startups"), "technology"),
    **dict.fromkeys(("science", "space", "environment", "health", "climate"), "science"),
    **dict.fromkeys(("sports", "sport", "cricket", "football", "tennis", "hockey",
                     "olympics", "badminton", "ipl"), "sports"),
    **dict.fromkeys(("entertainment", "movies", "bollywood", "hollywood", "music",
                     "television", "celebrity", "culture", "web-series", "ott"),
                    "entertainment"),
}


# Path words that mean "India" only on an Indian outlet's site. A British
# paper's /politics/ desk covers Westminster.
_INDIA_BY_NAME = {"india", "india-news"}

# Curated publications shown in the separate independent-India rail.
_INDEPENDENT_INDIA_SOURCES = {
    "scroll-in", "the-wire", "theprint", "newslaundry", "the-quint",
    "the-news-minute", "article-14", "reporters-collective", "the-caravan",
    "pari", "the-federal", "eastmojo", "boom-live", "alt-news", "factly",
}

# --- the Arbitration desk ----------------------------------------------------
#
# A story is filed here only when BOTH are true:
#   1. it uses arbitration's own words — arbitration, arbitral (tribunal,
#      award), arbitrator, or the Arbitration and Conciliation Act / "A&C Act";
#   2. it is about arbitration in India — the Act is named, a named Indian
#      court or an Indian place is, or an Indian outlet reports a court or a
#      section of the Act ("Section 37 Court", "U/S 34", "Supreme Court", "HC").
# and it is NOT about international, treaty or foreign-seated arbitration
# (SIAC, ICC, LCIA, DIFC, ICSID, investment treaties, foreign awards, a
# "global arbitration hub"), unless it is an Indian court proceeding under the
# Act's domestic sections. "Supreme Court" alone counts only from an Indian
# outlet, because a British paper's Supreme Court is in London.

_ARBITRATION_TERMS = re.compile(
    r"\b(?:arbitration|arbitral|arbitrator|arbitrators)\b|\bA\s?&\s?C\s+Act\b", re.I
)
_INDIAN_HIGH_COURTS = (
    r"allahabad|andhra pradesh|bombay|calcutta|chhattisgarh|delhi|gauhati|gujarat|"
    r"himachal pradesh|jammu (?:and|&) kashmir(?: and ladakh)?|jharkhand|karnataka|"
    r"kerala|madhya pradesh|madras|manipur|meghalaya|orissa|odisha|patna|"
    r"punjab (?:and|&) haryana|rajasthan|sikkim|telangana|tripura|uttarakhand"
)
# Indian on its face, whoever is reporting.
_INDIAN_ARBITRATION_CONTEXT = re.compile(
    r"arbitration and conciliation act|\bA\s?&\s?C\s+Act\b|domestic arbitration|"
    r"indian arbitration|supreme court of india|"
    rf"\b(?:{_INDIAN_HIGH_COURTS})\s+high\s+court\b|"
    r"\bindia(?:n|'s|’s)?\b",
    re.I,
)
_NAMED_INDIAN_COURT = re.compile(
    rf"supreme court of india|\b(?:{_INDIAN_HIGH_COURTS})\s+high\s+court\b", re.I
)
# Indian only because an Indian outlet is the one saying it.
_COURT_OR_SECTION = re.compile(
    r"\bsupreme court\b|\bhigh court\b|\bcommercial court\b|\bdistrict court\b|"
    r"\b(?:section|sec\.?|u/s\.?)\s*\d{1,2}[a-z]?\b",
    re.I,
)
_COURT_ABBREVIATION = re.compile(r"\b(?:SC|HC|NCLT|NCLAT)\b")  # case-sensitive
# Court work under Part I of the Act: domestic even when a foreign party is in it.
_PART_ONE_PROCEEDING = re.compile(
    r"domestic arbitration|"
    r"\b(?:section|sec\.?|u/s\.?)\s*(?:8|9|11|12|13|14|15|16|17|29a|31|33|34|36|37)\b",
    re.I,
)
_INTERNATIONAL_COMMERCIAL = re.compile(
    r"international (?:commercial )?arbitration|foreign[- ]seated|foreign (?:arbitral )?award|"
    r"treaty arbitration|investment treaty|investor[- ]state|\bISDS\b|\bICSID\b|"
    r"permanent court of arbitration|court of arbitration|\bSIAC\b|"
    r"singapore international arbitration|\bLCIA\b|london court of international|"
    r"\bHKIAC\b|\bDIFC\b|\bICC (?:arbitration|court|rules)\b|"
    r"(?:global|international) arbitration hub|indus waters",
    re.I,
)


def _is_domestic_indian_arbitration(text: str, *, indian_outlet: bool = False) -> bool:
    """Arbitration's own words AND an Indian hook, and not foreign arbitration."""
    if not _ARBITRATION_TERMS.search(text):
        return False
    court_hook = indian_outlet and bool(
        _COURT_OR_SECTION.search(text) or _COURT_ABBREVIATION.search(text)
    )
    indian = bool(
        _INDIAN_ARBITRATION_CONTEXT.search(text) or india_places_in(text) or court_hook
    )
    if not indian:
        return False
    part_one = bool(_PART_ONE_PROCEEDING.search(text)) and (
        court_hook or bool(_NAMED_INDIAN_COURT.search(text))
        or bool(re.search(r"arbitration and conciliation act|\bA\s?&\s?C\s+Act\b", text, re.I))
    )
    # International, treaty or foreign-seated arbitration belongs elsewhere —
    # unless an Indian court is hearing it under the Act's domestic sections.
    if _INTERNATIONAL_COMMERCIAL.search(text) and not part_one:
        return False
    # Abroad (a symposium in New Zealand, an arbitration in London) and no
    # Indian court or section in sight: not a domestic Indian matter.
    if foreign_places_in(text) and not (
        part_one or court_hook or _NAMED_INDIAN_COURT.search(text)
    ):
        return False
    return True


def url_section(url: str, *, indian_outlet: bool = True) -> str | None:
    """The category a publisher's own URL places the article in, if it says."""
    segments = [seg.lower() for seg in urlsplit(url or "").path.split("/") if seg]
    for segment in segments[:3]:
        slug = _URL_SECTIONS.get(segment)
        if slug is None:
            continue
        if slug == "india" and not indian_outlet and segment not in _INDIA_BY_NAME:
            continue
        return slug
    return None


def _is_indian_outlet(article: Article) -> bool:
    source = getattr(article, "source", None)
    country = getattr(source, "country", None)
    return country is None or country == "IN"


# Sections decided by where a story is, not what it is about.
_GEOGRAPHIC = {"india", "world"}


def _score_category(text: str, category: Category) -> int:
    """Weighted keyword hits on whole-word boundaries.

    Substring matching looks harmless until "approves" scores a hit for the
    technology keyword "app" and a bus lane is filed under Technology. A plural
    is still the same word, so "goals" counts for "goal".
    """
    lowered = text.lower()
    score = 0
    for keyword in category.keywords or []:
        keyword = (keyword or "").strip().lower()
        if not keyword:
            continue
        if re.search(rf"(?<!\w){re.escape(keyword)}(?:s|es)?(?!\w)", lowered):
            score += WEAK if keyword in WEAK_KEYWORDS else STRONG
    return score


def _geography(text: str, articles: list[Article]) -> str:
    """"india" or "world", from the places the story names."""
    lowered = text.lower()
    india = len(india_places_in(text))
    india += sum(1 for hint in INDIA_HINTS if re.search(rf"(?<!\w){re.escape(hint)}(?!\w)", lowered))
    foreign = len(foreign_places_in(text))
    foreign += len(set(_FOREIGN_ABBREVIATION.findall(text)))
    foreign += sum(
        1 for word in _FOREIGN_DEMONYMS if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", lowered)
    )

    if india and india >= foreign:
        return "india"
    if foreign:
        return "world"
    # No place named at all: go by who is reporting. An Indian outlet's
    # unplaced story is almost always domestic; an international one's is not.
    countries = Counter(
        (a.source.country or "").upper() for a in articles if a.source is not None
    )
    if countries and countries.most_common(1)[0][0] == "IN":
        return "india"
    return "world"


def categorise(articles: list[Article], categories: list[Category]) -> Category | None:
    """Pick the best category for a cluster of articles."""
    real = [c for c in categories if not c.is_synthetic and c.is_active]
    if not real:
        return None
    by_slug = {c.slug: c for c in real}

    # 0. Dedicated specialist sections. Arbitration is deliberately gated by
    #    both arbitration terminology and an Indian Act/court/section reference;
    #    a passing mention of arbitration is not enough. Independent-India is
    #    based on the curated publisher whitelist, not an opinion classifier.
    combined_text = clean_text(" ".join(
        f"{a.headline} {a.feed_summary or ''}" for a in articles
    ))
    if "arbitration" in by_slug and any(
        _is_domestic_indian_arbitration(
            clean_text(f"{a.headline} {a.feed_summary or ''}"),
            indian_outlet=_is_indian_outlet(a),
        )
        for a in articles
    ):
        return by_slug["arbitration"]
    # Team-BHP is a vehicle-specialist publisher; its reporting and member
    # submissions belong in the dedicated automobile section.
    if "automobile" in by_slug and any(
        a.source is not None and a.source.slug == "team-bhp" for a in articles
    ):
        return by_slug["automobile"]
    # Include the maintained Indian place gazetteer as well as explicit
    # national institutions. Many local investigations name only a district,
    # state or city and never repeat the word "India" in a short feed blurb.
    india_context = bool(
        re.search(
            r"\b(india|indian|delhi|mumbai|bengaluru|chennai|kolkata|hyderabad|"
            r"supreme court of india|parliament|lok sabha|rajya sabha)\b",
            combined_text, re.I,
        )
        or india_places_in(combined_text)
    )
    if "india-independent" in by_slug and india_context and any(
        a.source is not None
        and a.source.slug in _INDEPENDENT_INDIA_SOURCES
        and (a.source.country or "").upper() == "IN"
        for a in articles
    ):
        return by_slug["india-independent"]

    # 1. Where each report was filed. One vote per report: the desk named in
    #    its own URL when there is one, otherwise the section of the feed it
    #    arrived through.
    #
    #    The URL goes first because it describes that article, while a feed's
    #    label describes the feed — and some feeds are broader than their name.
    #    A business channel's "latest" feed carries its football coverage too,
    #    filed under /sports/ in the address; counting the feed's label put a
    #    striker's retirement in Business on the first live edition.
    votes: Counter[str] = Counter()
    filed_by_url: Counter[str] = Counter()
    for article in articles:
        section = url_section(
            article.canonical_url or article.url, indian_outlet=_is_indian_outlet(article)
        )
        query = article.discovery_query or ""
        topic = query.split(":", 1)[1] if query.startswith("topic:") else None
        if section in by_slug:
            votes[section] += 1
            filed_by_url[section] += 1
        elif topic in by_slug:
            # Search-feed labels are hints, not editorial decisions. Specialist
            # sections can only be assigned by their explicit eligibility gates.
            if topic == "india-independent":
                source = article.source
                if (
                    india_context
                    and source is not None
                    and source.slug in _INDEPENDENT_INDIA_SOURCES
                    and (source.country or "").upper() == "IN"
                ):
                    votes[topic] += 1
            elif topic == "arbitration":
                article_text = clean_text(
                    f"{article.headline} {article.feed_summary or ''}"
                )
                if _is_domestic_indian_arbitration(
                    article_text, indian_outlet=_is_indian_outlet(article)
                ):
                    votes[topic] += 1
            else:
                votes[topic] += 1
    if votes:
        most = max(votes.values())
        leaders = [slug for slug, count in votes.items() if count == most]
        # A tie goes to the section more outlets filed it under themselves,
        # then to what the story is about over where it happened.
        leaders.sort(key=lambda slug: (-filed_by_url[slug], slug in _GEOGRAPHIC, slug))
        return by_slug[leaders[0]]

    # 2. Feed tags.
    text_bits = []
    tag_votes = Counter()
    for article in articles:
        text_bits.append(f"{article.headline} {article.feed_summary or ''}")
        for tag in (article.raw or {}).get("tags", []) or []:
            tag_l = clean_text(str(tag)).lower()
            for category in real:
                if category.slug in {"arbitration", "india-independent"}:
                    continue  # specialist sections are assigned only by their explicit gates
                if tag_l == category.slug or tag_l == category.name.lower():
                    tag_votes[category.slug] += 2
    if tag_votes:
        return by_slug[tag_votes.most_common(1)[0][0]]

    # 3. Subject: business, technology, science, sports, entertainment.
    text = clean_text(" ".join(text_bits))
    subject_scores = {
        c.slug: _score_category(text, c)
        for c in real
        if c.slug not in _GEOGRAPHIC and c.slug not in {"arbitration", "india-independent"}
    }
    if subject_scores:
        best_slug, best_score = max(subject_scores.items(), key=lambda kv: kv[1])
        runner_up = sorted(subject_scores.values(), reverse=True)[1] if len(subject_scores) > 1 else 0
        if best_score >= MIN_SUBJECT_SCORE and best_score > runner_up:
            return by_slug[best_slug]

    # 4. Geography.
    return by_slug.get(_geography(text, articles)) or real[0]
