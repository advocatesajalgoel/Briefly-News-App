"""robots.txt gate.

Every outbound fetch passes through :func:`decide`. The rules are read the way
RFC 9309 says to read them, and when permission cannot be established the
answer is no: Briefly never fetches on the strength of "probably fine".

Why this is not ``urllib.robotparser``
--------------------------------------
The standard library's parser applies the *first* rule that matches, in file
order, and knows nothing of ``*`` or ``$``. The standard says the *most
specific* rule wins, with ``Allow`` winning a tie. The two disagree on the most
common shape a large site's file takes::

    User-agent: *
    Disallow: /
    Allow: /feeds/

Read first-match, that file forbids ``/feeds/``; read correctly, it grants it.
Getting it wrong in that direction breaks no publisher's rule, but it silently
discards sources the publisher chose to offer — and then reports "robots.txt
disallows this", which is untrue. Every refusal therefore carries its reason,
down to the rule that decided it, so the feed table shows what actually
happened instead of a guess.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

import httpx

from app.config import get_settings

_CACHE_TTL_SECONDS = 3600


# --- reading a robots file ---------------------------------------------------


@dataclass
class Rule:
    allow: bool
    pattern: str

    def matches(self, path: str) -> bool:
        return _compile(self.pattern).match(path) is not None


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None


_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _compile(pattern: str) -> re.Pattern[str]:
    """Turn a robots path pattern into a regex: ``*`` is any run, ``$`` ends."""
    compiled = _PATTERN_CACHE.get(pattern)
    if compiled is None:
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        regex = ".*".join(re.escape(part) for part in body.split("*"))
        compiled = re.compile(regex + ("$" if anchored else ""))
        _PATTERN_CACHE[pattern] = compiled
    return compiled


def parse(text: str) -> list[Group]:
    """Parse robots.txt into its groups. Anything unrecognised is ignored."""
    groups: list[Group] = []
    current: Group | None = None
    collecting_agents = False

    for raw_line in text.lstrip("﻿").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()

        if key == "user-agent":
            # Consecutive user-agent lines share one group; a user-agent line
            # after rules begins the next.
            if current is None or not collecting_agents:
                current = Group()
                groups.append(current)
            current.agents.append(value.lower())
            collecting_agents = True
            continue

        if current is None:
            continue
        if key in ("allow", "disallow"):
            collecting_agents = False
            if value:  # an empty Disallow means "nothing is disallowed"
                current.rules.append(Rule(allow=(key == "allow"), pattern=unquote(value)))
        elif key == "crawl-delay":
            collecting_agents = False
            try:
                current.crawl_delay = float(value)
            except ValueError:
                pass
        # Sitemap and unknown records neither carry rules nor end a group.
    return groups


def group_for(groups: list[Group], product_token: str) -> Group | None:
    """The group addressed to this crawler, falling back to ``*``.

    All groups naming the same agent are merged, as the standard requires.
    """
    token = product_token.lower()
    named = [g for g in groups if any(a != "*" and a and token.startswith(a) for a in g.agents)]
    chosen = named or [g for g in groups if "*" in g.agents]
    if not chosen:
        return None
    merged = Group(agents=sorted({a for g in chosen for a in g.agents}))
    for g in chosen:
        merged.rules.extend(g.rules)
        if merged.crawl_delay is None:
            merged.crawl_delay = g.crawl_delay
    return merged


def deciding_rule(group: Group | None, path: str) -> Rule | None:
    """The most specific matching rule; ``Allow`` wins a tie. None = no rule."""
    if group is None:
        return None
    best: Rule | None = None
    for rule in group.rules:
        if not rule.matches(path):
            continue
        if (
            best is None
            or len(rule.pattern) > len(best.pattern)
            or (len(rule.pattern) == len(best.pattern) and rule.allow and not best.allow)
        ):
            best = rule
    return best


# --- the gate ---------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


@dataclass
class _Entry:
    fetched_at: float
    groups: list[Group] | None = None  # None: no usable rules were obtained
    blanket: Decision | None = None  # set when the whole origin has one answer


def _product_token() -> str:
    return (get_settings().user_agent.split("/")[0] or "*").strip()


def _path_of(url: str) -> str:
    parts = urlsplit(url)
    path = unquote(parts.path) or "/"
    return f"{path}?{parts.query}" if parts.query else path


class RobotsCache:
    def __init__(self, ttl: int = _CACHE_TTL_SECONDS) -> None:
        self._cache: dict[str, _Entry] = {}
        self.ttl = ttl

    def _origin(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def _load(self, origin: str, client: httpx.Client | None = None) -> _Entry:
        settings = get_settings()
        robots_url = f"{origin}/robots.txt"
        owns_client = client is None
        client = client or httpx.Client(
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        )
        now = time.time()
        try:
            resp = client.get(robots_url)
        except Exception as exc:
            # Unreachable: the standard says assume nothing is permitted.
            return _Entry(now, blanket=Decision(
                False,
                f"robots.txt could not be fetched ({type(exc).__name__}), "
                "so permission was not established",
            ))
        finally:
            if owns_client:
                client.close()

        code = resp.status_code
        if 200 <= code < 300:
            return _Entry(now, groups=parse(resp.text))
        if code in (401, 403):
            # The standard would let a crawler proceed here. Briefly does not:
            # a site that refuses to show its rules to this bot is refusing
            # this bot, and that is respected rather than interpreted.
            return _Entry(now, blanket=Decision(
                False, f"robots.txt answered HTTP {code}; the site is treated as off limits"
            ))
        if code == 429 or code >= 500:
            return _Entry(now, blanket=Decision(
                False,
                f"robots.txt answered HTTP {code}, so permission was not established",
            ))
        # 404, 410 and the other 4xx: there is no robots file, so no restriction.
        return _Entry(now, groups=[])

    def get(self, url: str, client: httpx.Client | None = None) -> _Entry:
        origin = self._origin(url)
        entry = self._cache.get(origin)
        if entry and (time.time() - entry.fetched_at) < self.ttl:
            return entry
        entry = self._load(origin, client)
        self._cache[origin] = entry
        return entry

    def decide(self, url: str, *, client: httpx.Client | None = None) -> Decision:
        entry = self.get(url, client)
        if entry.blanket is not None:
            return entry.blanket
        group = group_for(entry.groups or [], _product_token())
        rule = deciding_rule(group, _path_of(url))
        if rule is None or rule.allow:
            return Decision(True)
        addressed_to = ", ".join(group.agents) if group else "*"
        return Decision(
            False,
            f"robots.txt disallows it: rule 'Disallow: {rule.pattern}' "
            f"for user-agent {addressed_to}",
        )

    def is_allowed(self, url: str, *, client: httpx.Client | None = None) -> bool:
        return self.decide(url, client=client).allowed

    def crawl_delay(self, url: str) -> float | None:
        entry = self.get(url)
        group = group_for(entry.groups or [], _product_token())
        return group.crawl_delay if group and group.crawl_delay else None

    def clear(self) -> None:
        self._cache.clear()


_ROBOTS = RobotsCache()


def decide(url: str, *, client: httpx.Client | None = None) -> Decision:
    """May this URL be fetched, and if not, exactly why not."""
    if not get_settings().respect_robots:  # pragma: no cover - pinned True by config
        return Decision(True)
    return _ROBOTS.decide(url, client=client)


def is_allowed(url: str, *, client: httpx.Client | None = None) -> bool:
    return decide(url, client=client).allowed


def crawl_delay(url: str) -> float | None:
    return _ROBOTS.crawl_delay(url)


def clear_cache() -> None:
    _ROBOTS.clear()
