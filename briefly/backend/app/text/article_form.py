"""What kind of item is this feed entry?

A feed mixes event reports with things that are not events: rolling live
pages, video clips, opinion columns, explainers, picture galleries, quizzes and
round-ups. Briefly's card answers one question — *what happened, and who
reported it* — so only reports can honestly become cards. Everything else is
left out at the door, and counted, rather than being squeezed into a shape it
does not have.

The classifier is deliberately dumb: URL sections and headline furniture that
publishers themselves use to label these forms. It never reads meaning into a
headline. When in doubt an item is a report, because wrongly dropping news is
the worse error.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

REPORT = "report"

_URL_FORMS: list[tuple[str, re.Pattern[str]]] = [
    # "/live/" as a section, or "live-updates"/"live-blog" anywhere in the slug —
    # but never a slug that merely starts with the word ("/live-wire-kills-two").
    ("live", re.compile(
        r"/live(?:/|$)|(?:^|[/-])live-?(?:blog|updates?|news)(?:[/-]|$)", re.I)),
    ("video", re.compile(r"/(?:videos?|watch|shorts|reels|newsfeed)(?:/|$)", re.I)),
    ("gallery", re.compile(
        r"/(?:photos?|photo-?gallery|gallery|galleries|pictures|in-?pics|web-?stories|"
        r"visual-?stories|slideshows?)(?:/|$)", re.I)),
    ("opinion", re.compile(
        r"/(?:opinions?|editorials?|columns?|columnists?|blogs?|op-?ed|commentisfree|"
        r"comment|letters|views|perspectives?)(?:/|$)", re.I)),
    ("explainer", re.compile(r"/(?:explained|explainers?|explainer-[^/]*|faq|know-your)(?:/|$)", re.I)),
    ("promo", re.compile(
        r"/(?:sponsored|brand-?(?:content|stories|post|wire)|advertorial|partner-?content|"
        r"press-?release|deals|coupons|horoscopes?|astrology|quiz(?:zes)?|crosswords?|"
        r"puzzles?|podcasts?)(?:/|$)", re.I)),
]

_HEADLINE_FORMS: list[tuple[str, re.Pattern[str]]] = [
    ("live", re.compile(
        r"^(?:live\b|.*\blive\s*[:|–]|.*\blive\s+updates?\b|.*\blive\s+blog\b|"
        r".*\|\s*live\b|.*\bhighlights\s*:)", re.I)),
    ("video", re.compile(r"^(?:watch|video|videos)\s*[:|\-–]|\bwatch\s+video\b|\(\s*video\s*\)$", re.I)),
    ("gallery", re.compile(r"^(?:in\s+pic(?:ture)?s|in\s+photos|photos?|pics|gallery)\s*[:|\-–]", re.I)),
    ("opinion", re.compile(
        r"^(?:opinion|editorial|comment|column|view|analysis|perspective|letters?)\s*[:|\-–]",
        re.I)),
    ("explainer", re.compile(
        r"^(?:explained|explainer|fact\s*check|faq|decoded|in\s+depth)\s*[:|\-–]|"
        r"^(?:why|how|what|who|where|when|which|is|are|was|were|can|could|will|would|should|"
        r"does|do|did)\b.*\?$|"
        r"^(?:why|how)\s+\S+|"
        r"\b(?:all\s+you\s+need\s+to\s+know|what\s+we\s+know(?:\s+so\s+far)?|"
        r"what\s+to\s+know|here(?:'|’)?s\s+(?:what|why|how)|things\s+to\s+know|"
        r"key\s+takeaways|explained\s*$|a\s+timeline)\b", re.I)),
    ("roundup", re.compile(
        r"^(?:morning|evening|daily|weekly|news)\s+(?:brief(?:ing)?|digest|wrap|round-?up|"
        r"headlines)\b|^top\s+\d+\b|\btop\s+(?:news|stories|headlines)\s+(?:of|today|this)\b|"
        r"^\d+\s+(?:things|ways|reasons|facts|takeaways|moments)\b|\bnews\s+wrap\b", re.I)),
    ("promo", re.compile(r"^(?:quiz|horoscope|crossword|sponsored|partner\s+content)\b", re.I)),
]


def article_form(headline: str, url: str = "") -> str:
    """Return ``"report"`` or the name of the non-report form the item takes."""
    path = urlsplit(url).path if url else ""
    for form, pattern in _URL_FORMS:
        if pattern.search(path):
            return form
    text = (headline or "").strip()
    # A headline that is nothing but a question is asking, not reporting.
    for form, pattern in _HEADLINE_FORMS:
        if pattern.search(text):
            return form
    if text.endswith("?"):
        return "explainer"
    return REPORT


def is_report(headline: str, url: str = "") -> bool:
    return article_form(headline, url) == REPORT
