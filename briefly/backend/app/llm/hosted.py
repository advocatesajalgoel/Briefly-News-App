"""Anthropic and OpenAI extraction backends.

Both speak the same :class:`~app.llm.schema.ExtractionResult` contract, both are
optional, and both fall back to the rule-based provider when no credential is
configured — so a missing key degrades quality, never availability.

Credentials are read from the environment on the server. Nothing here is ever
compiled into the iOS app.
"""

from __future__ import annotations

import json
import re

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.llm import prompts
from app.llm.rule_based import RuleBasedProvider
from app.llm.schema import ExtractionProvider, ExtractionResult, FactCandidate, SourceDocument

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json(payload: str) -> dict:
    payload = (payload or "").strip()
    if payload.startswith("```"):
        payload = re.sub(r"^```(?:json)?\s*|\s*```$", "", payload, flags=re.DOTALL)
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(payload)
        if not match:
            raise
        return json.loads(match.group(0))


def _result_from_payload(data: dict, provider: str) -> ExtractionResult:
    facts = []
    for raw in data.get("facts", []) or []:
        if not isinstance(raw, dict) or not raw.get("text"):
            continue
        facts.append(
            FactCandidate(
                slot=str(raw.get("slot", "other")),
                kind=str(raw.get("kind", "attributed")),
                text=str(raw["text"]),
                attributed_to=raw.get("attributed_to") or None,
                evidence=raw.get("evidence") or None,
                source_index=raw.get("source_index"),
                confidence=float(raw.get("confidence") or 0.5),
                salience=float(raw.get("salience") or 0.5),
            ).normalised()
        )
    clauses = []
    for raw in data.get("summary_clauses", []) or []:
        if isinstance(raw, dict) and raw.get("text"):
            clauses.append(
                {
                    "text": str(raw["text"]),
                    "priority": int(raw.get("priority", 50)),
                    "required": bool(raw.get("required", False)),
                    "slot": str(raw.get("slot", "other")),
                }
            )
    return ExtractionResult(
        headline=str(data.get("headline") or ""),
        dek=str(data.get("dek") or ""),
        facts=facts,
        summary_clauses=clauses,
        provider=provider,
    )


class _HostedProvider(ExtractionProvider):
    """Shared plumbing: fall back to rule-based whenever anything goes wrong."""

    name = "hosted"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.settings = get_settings()
        self._client = client
        self._fallback = RuleBasedProvider()

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.settings.llm_timeout_seconds)
        return self._client

    def _fallback_result(self, documents, reason: str) -> ExtractionResult:
        result = self._fallback.extract(documents)
        result.warnings.append(f"{self.name} unavailable ({reason}); used rule_based")
        return result

    def _merge_with_rule_based(
        self, hosted: ExtractionResult, documents: list[SourceDocument]
    ) -> ExtractionResult:
        """Keep the model's prose, but never lose the deterministic skeleton.

        The rule-based pass reliably finds the numbers, dates and source
        agreement counts. Merging keeps those even if the model omits them.
        """
        base = self._fallback.extract(documents)
        have = {(f.slot, f.text.lower()) for f in hosted.facts}
        for fact in base.facts:
            if fact.slot in {"number", "date"} and (fact.slot, fact.text.lower()) not in have:
                hosted.facts.append(fact)
        if not hosted.headline:
            hosted.headline = base.headline
        if not hosted.summary_clauses:
            hosted.summary_clauses = base.summary_clauses
        if not hosted.dek:
            hosted.dek = base.dek
        return hosted

    def write_narration(self, story_brief: dict, target_words: int, mode: str = "daily") -> str:
        try:
            text = self._complete(
                prompts.NARRATION_SYSTEM,
                prompts.build_narration_prompt(story_brief, target_words, mode),
            )
            if text and len(text.split()) >= max(20, target_words // 4):
                return text.strip()
        except Exception:
            pass
        return self._fallback.write_narration(story_brief, target_words, mode)

    def _complete(self, system: str, user: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class AnthropicProvider(_HostedProvider):
    name = "anthropic"
    endpoint = "https://api.anthropic.com/v1/messages"
    api_version = "2023-06-01"

    def available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _complete(self, system: str, user: str) -> str:
        resp = self._http().post(
            self.endpoint,
            headers={
                "x-api-key": self.settings.anthropic_api_key,
                "anthropic-version": self.api_version,
                "content-type": "application/json",
            },
            json={
                "model": self.settings.llm_model,
                "max_tokens": self.settings.llm_max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        body = resp.json()
        return "".join(
            block.get("text", "") for block in body.get("content", []) if block.get("type") == "text"
        )

    def extract(self, documents: list[SourceDocument]) -> ExtractionResult:
        if not self.available():
            return self._fallback_result(documents, "ANTHROPIC_API_KEY not set")
        try:
            raw = self._complete(prompts.SYSTEM, prompts.build_user_prompt(documents))
            result = _result_from_payload(_parse_json(raw), self.name)
        except Exception as exc:
            return self._fallback_result(documents, f"{type(exc).__name__}: {exc}")
        return self._merge_with_rule_based(result, documents)


class OpenAIProvider(_HostedProvider):
    name = "openai"
    endpoint = "https://api.openai.com/v1/chat/completions"

    def available(self) -> bool:
        return bool(self.settings.openai_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _complete(self, system: str, user: str) -> str:
        resp = self._http().post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.llm_model,
                "max_tokens": self.settings.llm_max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        body = resp.json()
        return body["choices"][0]["message"]["content"]

    def extract(self, documents: list[SourceDocument]) -> ExtractionResult:
        if not self.available():
            return self._fallback_result(documents, "OPENAI_API_KEY not set")
        try:
            raw = self._complete(prompts.SYSTEM, prompts.build_user_prompt(documents))
            result = _result_from_payload(_parse_json(raw), self.name)
        except Exception as exc:
            return self._fallback_result(documents, f"{type(exc).__name__}: {exc}")
        return self._merge_with_rule_based(result, documents)
