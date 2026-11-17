"""Editorial guard rails.

Briefly's promise is "maximum transparency, minimum editorial distortion", not
"we are unbiased". This module enforces the parts of that promise a machine can
actually check: no sensational or emotive framing, no unattributed allegation
presented as fact, no speculation stated flatly, no opinion verbs.

It returns findings; the caller decides whether to rewrite, downgrade or flag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Loaded / sensational vocabulary. Matched as whole words, case-insensitive.
SENSATIONAL = {
    "slammed", "blasted", "lashed out", "shocking", "shocked", "stunning",
    "stunned", "bombshell", "outrageous", "outrage", "fury",
    "furious", "slams", "blasts", "destroys", "demolished", "humiliated",
    "meltdown", "chaos", "carnage", "catastrophic", "nightmare",
    "unbelievable", "incredible", "insane", "crazy", "epic", "massive blow",
    "brutal", "savage", "mocked", "trolled", "war of words",
    "you won't believe", "must see", "viral sensation", "heartbreaking",
    "terrifying", "horrific", "devastating", "miracle",
}
# Words above that are ordinary vocabulary in some contexts. "Disaster" and
# "storm" are plain descriptions in weather and civil-defence reporting
# ("the state disaster authority", "the storm made landfall"), and "explosive"
# is the literal word in "an explosive device was found", so they are not on
# the list at all — flagging them would teach the pipeline to avoid the
# correct word.

OPINION_MARKERS = {
    "clearly", "obviously", "undoubtedly", "certainly", "surely", "of course",
    "everyone knows", "it is clear that", "there is no doubt", "rightly",
    "wrongly", "shamefully", "disgracefully", "correctly", "sadly",
    "fortunately", "unfortunately", "thankfully", "predictably", "as expected",
    "needless to say", "arguably", "in my view", "we believe", "should have",
    "must be held", "deserves",
}

SPECULATION_MARKERS = {
    "could", "might", "may", "likely", "expected to", "set to", "poised to",
    "reportedly", "rumoured", "rumored", "speculation", "believed to",
    "is said to", "sources say", "insiders say", "on track to",
}

# Words that assert wrongdoing. Legal for us only when attributed.
ALLEGATION_TERMS = {
    "guilty", "fraud", "fraudulent", "corrupt", "corruption", "bribe",
    "bribery", "scam", "criminal", "illegal", "lied", "lying", "cheated",
    "stole", "theft", "embezzled", "laundering", "conspiracy", "colluded",
    "rigged", "murdered", "assaulted", "abused", "trafficking", "smuggling",
}

ATTRIBUTION_TERMS = {
    "according to", "said", "says", "stated", "told", "alleged", "alleges",
    "allegedly", "claimed", "claims", "accused", "denied", "denies",
    "reported", "reports", "per ", "attributed", "quoted", "in a statement",
    "the complaint", "the fir", "the chargesheet", "police said",
    "the court", "the petition", "disputed", "disputes", "maintains",
}

DISPUTE_TERMS = {
    "disputed", "denied", "denies", "rejected", "contradicted", "contested",
    "refuted", "pushed back", "questioned", "challenged", "differs",
    "conflicting", "no independent confirmation", "could not be verified",
    "unverified",
}

CONFIRMATION_TERMS = {
    "confirmed", "confirms", "official statement", "in a statement",
    "announced", "notified", "gazette", "press release", "verified",
    "acknowledged",
}


def _phrase_pattern(terms: set[str]) -> re.Pattern[str]:
    parts = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"(?<![\w])(?:" + "|".join(parts) + r")(?![\w])", re.IGNORECASE)


_SENSATIONAL_RE = _phrase_pattern(SENSATIONAL)
_OPINION_RE = _phrase_pattern(OPINION_MARKERS)
_SPECULATION_RE = _phrase_pattern(SPECULATION_MARKERS)
_ALLEGATION_RE = _phrase_pattern(ALLEGATION_TERMS)
_ATTRIBUTION_RE = _phrase_pattern(ATTRIBUTION_TERMS)
_DISPUTE_RE = _phrase_pattern(DISPUTE_TERMS)
_CONFIRMATION_RE = _phrase_pattern(CONFIRMATION_TERMS)


@dataclass
class StyleFinding:
    code: str
    message: str
    matches: list[str] = field(default_factory=list)
    severity: str = "warning"


@dataclass
class StyleReport:
    findings: list[StyleFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "blocker" for f in self.findings)

    @property
    def clean(self) -> bool:
        return not self.findings

    def codes(self) -> list[str]:
        return [f.code for f in self.findings]

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "findings": [
                {
                    "code": f.code,
                    "message": f.message,
                    "matches": f.matches,
                    "severity": f.severity,
                }
                for f in self.findings
            ],
        }


def has_attribution(text: str) -> bool:
    return bool(_ATTRIBUTION_RE.search(text or ""))


def mentions_dispute(text: str) -> bool:
    return bool(_DISPUTE_RE.search(text or ""))


def mentions_confirmation(text: str) -> bool:
    return bool(_CONFIRMATION_RE.search(text or ""))


def check(text: str, *, require_attribution_for_allegations: bool = True) -> StyleReport:
    """Inspect a piece of Briefly-authored prose."""
    report = StyleReport()
    text = text or ""

    if m := sorted({x.lower() for x in _SENSATIONAL_RE.findall(text)}):
        report.findings.append(
            StyleFinding("sensational_language", "Sensational or emotive wording", m, "blocker")
        )
    if m := sorted({x.lower() for x in _OPINION_RE.findall(text)}):
        report.findings.append(
            StyleFinding("opinion_marker", "Opinionated or editorialising wording", m, "blocker")
        )

    allegations = sorted({x.lower() for x in _ALLEGATION_RE.findall(text)})
    if allegations and require_attribution_for_allegations and not has_attribution(text):
        report.findings.append(
            StyleFinding(
                "unattributed_allegation",
                "Wrongdoing described without naming who alleges it",
                allegations,
                "blocker",
            )
        )

    speculation = sorted({x.lower() for x in _SPECULATION_RE.findall(text)})
    if speculation and not has_attribution(text):
        report.findings.append(
            StyleFinding(
                "unattributed_speculation",
                "Speculative wording with no source attached",
                speculation,
                "warning",
            )
        )

    if re.search(r"!{1,}", text):
        report.findings.append(
            StyleFinding("exclamation", "Exclamation marks are not used in Briefly copy", ["!"])
        )
    if re.search(r"\b[A-Z]{4,}\b", text):
        caps = sorted(set(re.findall(r"\b[A-Z]{4,}\b", text)))
        allowed = {"NASA", "OPEC", "NATO", "UNSC", "GDP", "SEBI", "RBI", "ISRO",
                   "NDTV", "IPCC", "WHO", "IMF", "OECD", "BRICS", "NCLT", "CBI",
                   "NIA", "TRAI", "UIDAI", "GST", "UPI", "IPO", "AQI"}
        stray = [c for c in caps if c not in allowed]
        if stray:
            report.findings.append(
                StyleFinding("shouting_caps", "All-caps words read as shouting", stray)
            )

    return report


def neutralise(text: str) -> str:
    """Replace the most common loaded verbs with plain ones.

    Only used on Briefly-authored drafts, never on a publisher's own headline —
    a publisher's headline is quoted as they wrote it, in the sources list.
    """
    replacements = {
        r"\bslammed\b": "criticised",
        r"\bslams\b": "criticises",
        r"\bblasted\b": "criticised",
        r"\bblasts\b": "criticises",
        r"\blashed out at\b": "criticised",
        r"\bhit out at\b": "criticised",
        r"\bshocking\b": "unexpected",
        r"\bstunning\b": "unexpected",
        r"\bbombshell\b": "unexpected",
        r"\bchaos\b": "disruption",
        r"\bfury\b": "objections",
        r"\boutrage\b": "objections",
        r"\bmassive\b": "large",
        r"\bhuge\b": "large",
        r"\bcrisis\b": "situation",
    }
    out = text
    for pattern, repl in replacements.items():
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out
