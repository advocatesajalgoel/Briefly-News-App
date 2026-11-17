"""Cleaning and lightweight linguistic helpers used across the pipeline."""

from __future__ import annotations

import html
import re
import unicodedata
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.text.wordcount import normalise_whitespace

_TAG_RE = re.compile(r"<[^>]+>")
_MULTISPACE = re.compile(r"\s+")

# Tracking parameters that change the URL without changing the article.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_reader", "gclid", "fbclid", "igshid", "mc_cid",
    "mc_eid", "ref", "referrer", "source", "cmpid", "CMP", "at_medium",
    "at_campaign", "smid", "partner", "ncid", "__twitter_impression",
}

STOPWORDS = {
    "a", "about", "after", "again", "against", "all", "also", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being",
    "between", "both", "but", "by", "can", "did", "do", "does", "doing", "down",
    "during", "each", "for", "from", "further", "had", "has", "have", "having",
    "he", "her", "here", "hers", "him", "his", "how", "i", "if", "in", "into",
    "is", "it", "its", "just", "me", "more", "most", "my", "no", "nor", "not",
    "now", "of", "off", "on", "once", "only", "or", "other", "our", "out",
    "over", "own", "s", "same", "she", "should", "so", "some", "such", "t",
    "than", "that", "the", "their", "them", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very",
    "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "whom", "why", "will", "with", "would", "you", "your", "says", "say",
    "said", "new", "news", "report", "reports", "reported", "amid", "ahead",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return normalise_whitespace(text)


def clean_text(text: str | None, *, max_chars: int | None = None) -> str:
    out = strip_html(text)
    out = unicodedata.normalize("NFKC", out)
    out = _MULTISPACE.sub(" ", out).strip()
    if max_chars is not None and len(out) > max_chars:
        cut = out[:max_chars]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        out = cut.rstrip(",;:- ") + "…"
    return out


def canonical_url(url: str) -> str:
    """Strip tracking noise so the same article from two feeds dedupes."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if (scheme == "https" and netloc.endswith(":443")) or (
        scheme == "http" and netloc.endswith(":80")
    ):
        netloc = netloc.rsplit(":", 1)[0]
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in {p.lower() for p in _TRACKING_PARAMS}
    ]
    query.sort()
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def registered_domain(url: str) -> str:
    host = urlsplit(url).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def tokenize(text: str, *, drop_stopwords: bool = True, min_len: int = 2) -> list[str]:
    toks = _TOKEN_RE.findall(clean_text(text).lower())
    out = []
    for t in toks:
        if len(t) < min_len:
            continue
        if drop_stopwords and t in STOPWORDS:
            continue
        out.append(t)
    return out


def shingles(tokens: list[str], n: int = 3) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


_CAP_SEQ_RE = re.compile(
    r"\b(?:[A-Z][\w’'&.\-]*)(?:\s+(?:of|and|for|the|de|al|bin)?\s*[A-Z][\w’'&.\-]*)*\b"
)
_SENTENCE_START_RE = re.compile(r"(?:^|(?<=[.!?]\s))")

# Words that are capitalised for reasons other than being a proper noun.
_NOT_ENTITIES = {
    "The", "A", "An", "This", "That", "These", "Those", "It", "He", "She",
    "They", "We", "You", "I", "But", "And", "In", "On", "At", "For", "After",
    "Before", "During", "While", "However", "Meanwhile", "Also", "New",
    "Breaking", "Update", "Exclusive", "Watch", "Live", "Read", "Video",
    "Photos", "Opinion", "Analysis", "Explained", "Here", "There", "What",
    "Why", "How", "When", "Where", "Who", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday", "Sunday", "January", "February", "March",
    "April", "May", "June", "July", "August", "September", "October",
    "November", "December", "Today", "Yesterday", "Tomorrow",
}


def _sentence_chunks(text: str) -> list[str]:
    """Split on sentence boundaries so a capitalised phrase can never span one."""
    return [c for c in re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9“\"'])", text) if c.strip()]


def extract_entities(text: str, *, min_len: int = 3, limit: int = 24) -> list[str]:
    """Capitalisation-based proper-noun candidates.

    Deliberately conservative: this feeds clustering and the ``who``/``where``
    slots, and a wrong entity is worse than a missing one. Anything the pipeline
    asserts to a reader is checked back against the source text separately.
    """
    cleaned = clean_text(text)
    found: list[str] = []
    seen: set[str] = set()
    matches = [m for chunk in _sentence_chunks(cleaned) for m in _CAP_SEQ_RE.finditer(chunk)]
    for match in matches:
        phrase = match.group(0).strip(" .,'’-")
        phrase = re.sub(r"[’']s\b", "", phrase).strip()
        if not phrase or len(phrase) < min_len:
            continue
        head = phrase.split()[0]
        if head in _NOT_ENTITIES and len(phrase.split()) == 1:
            continue
        # Drop a leading determiner-like capital that only starts the sentence.
        parts = phrase.split()
        while parts and parts[0] in _NOT_ENTITIES:
            parts = parts[1:]
        if not parts:
            continue
        phrase = " ".join(parts)
        if len(phrase) < min_len:
            continue
        if phrase.isupper() and len(phrase) <= 2:
            continue
        key = phrase.lower()
        if key in seen or key in STOPWORDS:
            continue
        seen.add(key)
        found.append(phrase)
        if len(found) >= limit:
            break
    return found


@lru_cache(maxsize=65536)
def entity_key(entity: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", entity.lower()).strip()


_NUMBER_RE = re.compile(
    r"(?<![\w.])"
    r"(?:(?:₹|Rs\.?|INR|\$|US\$|€|£)\s?)?"
    r"\d[\d,]*(?:\.\d+)?"
    r"(?:\s?(?:per\s?cent|percent|%|crore|lakh|billion|million|trillion|thousand|"
    r"bn|mn|km|kg|tonnes?|people|deaths?|points?|basis\s?points|bps|MW|GW))?",
    re.IGNORECASE,
)


def extract_numbers(text: str, limit: int = 12) -> list[str]:
    cleaned = clean_text(text)
    out: list[str] = []
    seen: set[str] = set()
    for m in _NUMBER_RE.finditer(cleaned):
        val = m.group(0).strip()
        if not any(ch.isdigit() for ch in val):
            continue
        # Skip bare years unless they carry a unit; dates are handled separately.
        if re.fullmatch(r"(19|20)\d{2}", val):
            continue
        if val.lower() in seen:
            continue
        seen.add(val.lower())
        out.append(val)
        if len(out) >= limit:
            break
    return out


_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
_DATE_RE = re.compile(
    rf"\b(?:\d{{1,2}}\s+(?:{_MONTHS})(?:\s+\d{{4}})?"
    rf"|(?:{_MONTHS})\s+\d{{1,2}}(?:,\s*\d{{4}})?"
    rf"|(?:{_MONTHS})\s+(?:19|20)\d{{2}}"
    rf"|\d{{4}}-\d{{2}}-\d{{2}}"
    rf"|(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
    rf"|(?:today|yesterday|tomorrow|this week|next week|last week|this month)"
    rf"|(?:19|20)\d{{2}})\b",
    re.IGNORECASE,
)


def extract_dates(text: str, limit: int = 8) -> list[str]:
    cleaned = clean_text(text)
    out: list[str] = []
    seen: set[str] = set()
    for m in _DATE_RE.finditer(cleaned):
        val = m.group(0).strip()
        if val.lower() in seen:
            continue
        seen.add(val.lower())
        out.append(val)
        if len(out) >= limit:
            break
    return out
