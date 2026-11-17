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

_ARBITRATION_TERMS = re.compile(
    r"\b(arbitration|arbitral|arbitrator|arbitrators)\b", re.I
)
_INDIAN_ARBITRATION_CONTEXT = re.compile(
    r"(arbitration and conciliation act|domestic arbitration|indian arbitration law|"
    r"supreme court of india|delhi high court|bombay high court|calcutta high court|"
    r"madras high court|karnataka high court|kerala high court|allahabad high court|"
    r"punjab and haryana high court|gujarat high court|rajasthan high court|"
    r"patna high court|indian court.{0,45}arbitration|arbitration.{0,45}indian court|"
    r"india.{0,45}arbitration|arbitration.{0,45}india|"
    r"section\s+(9|11|12|14|15|16|17|29a|31|34|36|37).{0,45}arbitration act)",
    re.I,
)
_INTERNATIONAL_COMMERCIAL = re.compile(
    r"international commercial arbitration|foreign-seated arbitration|"
    r"foreign seated arbitration|treaty arbitration", re.I
)


def _is_domestic_indian_arbitration(text: str) -> bool:
    """Conservative gate: arbitration terminology AND a clear Indian-law/court hook."""
    if not _ARBITRATION_TERMS.search(text):
        return False
    if not _INDIAN_ARBITRATION_CONTEXT.search(text):
        return False
    # Do not sweep international/treaty arbitration into this domestic section
    # unless the report also squarely concerns a domestic Indian court proceeding.
    if _INTERNATIONAL_COMMERCIAL.search(text) and not re.search(
        r"domestic arbitration|section\s+(9|11|34|37)", text, re.I
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
    if "arbitration" in by_slug and _is_domestic_indian_arbitration(combined_text):
        return by_slug["arbitration"]
    india_context = bool(re.search(
        r"\b(india|indian|delhi|mumbai|bengaluru|chennai|kolkata|hyderabad|"
        r"supreme court of india|parliament|lok sabha|rajya sabha)\b",
        combined_text, re.I,
    ))
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
                if tag_l == category.slug or tag_l == category.name.lower():
                    tag_votes[category.slug] += 2
    if tag_votes:
        return by_slug[tag_votes.most_common(1)[0][0]]

    # 3. Subject: business, technology, science, sports, entertainment.
    text = clean_text(" ".join(text_bits))
    subject_scores = {
        c.slug: _score_category(text, c) for c in real if c.slug not in _GEOGRAPHIC
    }
    if subject_scores:
        best_slug, best_score = max(subject_scores.items(), key=lambda kv: kv[1])
        runner_up = sorted(subject_scores.values(), reverse=True)[1] if len(subject_scores) > 1 else 0
        if best_score >= MIN_SUBJECT_SCORE and best_score > runner_up:
            return by_slug[best_slug]

    # 4. Geography.
    return by_slug.get(_geography(text, articles)) or real[0]
