"""Prompts for hosted extraction backends.

These prompts are *instructions*, not guarantees. Everything they ask for is
independently enforced afterwards: grounding by ``app/pipeline/facts.py`` and
length by ``app/text/wordcount.py``. If the model ignores the prompt, the
pipeline still cannot publish an unsupported or over-length claim.
"""

from __future__ import annotations

import json

from app.llm.schema import SourceDocument

SYSTEM = """You are the extraction stage of Briefly, a news application whose \
stated standard is "maximum transparency, minimum editorial distortion". You are \
not asked to summarise. You are asked to extract structured facts.

Absolute rules:
1. Use ONLY the supplied material. Never add background knowledge, however certain.
2. Never turn an allegation, claim or projection into a fact. If somebody said it, \
   record who.
3. Never invent a number, name, date, quote, source or URL. Copy figures exactly \
   as they appear.
4. Where sources disagree, record kind="disputed" and name both sides.
5. Where the material hedges ("may", "reportedly", "sources say"), record \
   kind="uncertain".
6. Every fact must carry an `evidence` field containing a VERBATIM span from the \
   supplied material that supports it. Facts without a verbatim span are discarded.
7. Neutral register only: no loaded verbs, no adjectives of judgement, no \
   speculation of your own, no exclamation marks.

Return a single JSON object and nothing else."""

SCHEMA_HINT = """{
  "headline": "neutral factual headline, 8-14 words, no publisher branding",
  "dek": "one or two neutral sentences of additional context",
  "facts": [
    {
      "slot": "who|what|when|where|why|number|date|other",
      "kind": "confirmed|attributed|disputed|number|date|context|uncertain",
      "text": "the fact, stated plainly",
      "attributed_to": "who said it, or null when several independent sources report it directly",
      "evidence": "verbatim span copied from the supplied material",
      "source_index": 0,
      "confidence": 0.0,
      "salience": 0.0
    }
  ],
  "summary_clauses": [
    {"text": "clause for the card", "priority": 100, "required": true, "slot": "what"}
  ]
}"""

USER_TEMPLATE = """Below are {n} report(s) that a clustering step has determined \
describe the same event. Only the publisher's own headline and the short blurb \
they syndicate are available — there is no full article text, so do not pretend \
to have read one.

{documents}

Extract the structured facts. Fill who / what / when / where / why, plus every \
important number and date. Mark kind="confirmed" only when two or more \
independent publishers state the same thing directly, or an official source \
does. Everything else is "attributed" (name the speaker), "disputed" (name both \
sides) or "uncertain".

Then propose `summary_clauses`: short fragments a downstream word-budget will \
assemble into a card of AT MOST 30 words. Exactly one clause must have \
"required": true — the core event. Order the rest by how much a reader would \
lose without them. Do not attempt to hit 30 words yourself; propose more than \
fits and let the budget choose.

Respond with JSON matching this shape:
{schema}"""


def render_documents(documents: list[SourceDocument]) -> str:
    blocks = []
    for doc in documents:
        blocks.append(
            "\n".join(
                [
                    f"[{doc.index}] SOURCE: {doc.source_name} ({doc.source_kind})",
                    f"    PUBLISHED: {doc.published_at or 'unknown'}",
                    f"    HEADLINE: {doc.headline}",
                    f"    BLURB: {doc.summary or '(headline only — this publisher syndicates no summary)'}",
                ]
            )
        )
    return "\n\n".join(blocks)


def build_user_prompt(documents: list[SourceDocument]) -> str:
    return USER_TEMPLATE.format(
        n=len(documents), documents=render_documents(documents), schema=SCHEMA_HINT
    )


NARRATION_SYSTEM = """You are the narration stage of Briefly, a spoken news \
briefing. You write for the ear: short sentences, no lists, no headings, no \
stage directions, no markup.

Absolute rules:
1. Work ONLY from the structured facts supplied. Never add anything else.
2. Never read a publisher's sentences back. Write original narration.
3. Attribute: "according to Reuters", "officials said", "the government stated", \
   "opposition leaders disputed".
4. Say plainly what is confirmed, what is only claimed, and where sources differ.
5. Explain; do not persuade. No opinions, no predictions of your own, no \
   rhetorical questions.
6. Numbers and names exactly as given."""


NARRATION_TEMPLATE = """Write approximately {target_words} words of spoken \
narration for this story. Mode: {mode}.

STRUCTURED FACTS
{brief}

{structure}

Return plain prose only."""

DAILY_STRUCTURE = """Cover, in order: what happened, who reported it and how many \
independent sources, the key figures, and any disagreement between sources. One \
paragraph."""

DEEP_DIVE_STRUCTURE = """Cover, in this order, as flowing narration rather than \
headed sections: what happened; what is confirmed and by whom; what different \
sources report; where sources disagree; why it matters, framed only in terms of \
what the facts state; and what happens next according to the sources. If the \
material does not say what happens next, say that it does not."""


def build_narration_prompt(brief: dict, target_words: int, mode: str) -> str:
    structure = DEEP_DIVE_STRUCTURE if mode == "deep_dive" else DAILY_STRUCTURE
    return NARRATION_TEMPLATE.format(
        target_words=target_words,
        mode=mode,
        brief=json.dumps(brief, indent=2, ensure_ascii=False, default=str),
        structure=structure,
    )
