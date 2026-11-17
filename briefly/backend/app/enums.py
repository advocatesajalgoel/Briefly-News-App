"""Shared enumerations. Values are stored as short strings in Postgres."""

from __future__ import annotations

from enum import StrEnum


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FLAGGED = "flagged"
    PUBLISHED = "published"
    FAILED = "failed"
    ARCHIVED = "archived"


class SourceKind(StrEnum):
    """What sort of publisher a source is. Drives the diversity indicator."""

    NATIONAL = "national"          # national-scale publication
    INTERNATIONAL = "international"
    REGIONAL = "regional"
    WIRE = "wire"                  # news agency / wire service
    OFFICIAL = "official"          # government or institutional primary source
    AGGREGATOR = "aggregator"      # discovery feed only, never counted as a source
    OTHER = "other"


class SourceAccess(StrEnum):
    """How much of the source we may legitimately use."""

    FEED_FULL = "feed_full"        # feed carries a usable summary
    FEED_HEADLINE = "feed_headline"  # feed carries a headline only
    RESTRICTED = "restricted"      # paywalled / disallowed: link out only


class FactKind(StrEnum):
    CONFIRMED = "confirmed"        # stated as fact by 2+ independent sources or an official source
    ATTRIBUTED = "attributed"      # someone said it; we name who
    DISPUTED = "disputed"          # sources or parties contradict each other
    NUMBER = "number"
    DATE = "date"
    CONTEXT = "context"
    UNCERTAIN = "uncertain"        # explicitly hedged in the source


class FactSlot(StrEnum):
    WHO = "who"
    WHAT = "what"
    WHEN = "when"
    WHERE = "where"
    WHY = "why"
    NUMBER = "number"
    DATE = "date"
    OTHER = "other"


class EpisodeKind(StrEnum):
    DAILY = "daily"
    DEEP_DIVE = "deep_dive"


class DiversityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class QCSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"
