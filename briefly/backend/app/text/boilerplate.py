"""Sentences a publisher staples to every item in its feed.

"Continue reading...", "This story has been published from a wire agency feed
without modifications to the text." Furniture like this is not about anything,
but it is *shared*, and shared words are what the clusterer reads as two
reports covering one event. Left in, it can weld a publisher's whole feed into
a single story; it can also surface in a summary as though it were a fact.

The test is mechanical and local to one feed: a sentence that turns up in
several of a feed's items is furniture. Nothing is decided by what it says.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_NOT_WORD = re.compile(r"[^a-z0-9]+")

# A real sentence can recur across a feed — three items on one event may open
# alike — so it takes both a count and a share of the feed to call it furniture.
MIN_ITEMS = 3
MIN_SHARE = 0.20
MIN_LENGTH = 12


def _key(sentence: str) -> str:
    return _NOT_WORD.sub(" ", sentence.lower()).strip()


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text or "") if s.strip()]


def repeated_sentences(texts: list[str]) -> set[str]:
    """Normalised sentences that recur across ``texts`` often enough to be furniture."""
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update({k for k in (_key(s) for s in sentences(text)) if len(k) >= MIN_LENGTH})
    needed = max(MIN_ITEMS, math.ceil(len(texts) * MIN_SHARE))
    return {key for key, count in counts.items() if count >= needed}


def strip_repeated(text: str, repeated: set[str]) -> str:
    if not text or not repeated:
        return text
    return " ".join(s.strip() for s in sentences(text) if _key(s) not in repeated).strip()
