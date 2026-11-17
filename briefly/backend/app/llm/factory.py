"""Choose the configured extraction backend."""

from __future__ import annotations

from app.config import get_settings
from app.llm.rule_based import RuleBasedProvider
from app.llm.schema import ExtractionProvider

_REGISTRY: dict[str, type[ExtractionProvider]] = {}


def register(name: str, cls: type[ExtractionProvider]) -> None:
    _REGISTRY[name] = cls


def get_extraction_provider(name: str | None = None) -> ExtractionProvider:
    settings = get_settings()
    name = (name or settings.llm_provider or "rule_based").lower()

    if name in _REGISTRY:
        return _REGISTRY[name]()
    if name == "rule_based":
        return RuleBasedProvider()
    if name == "anthropic":
        from app.llm.hosted import AnthropicProvider

        return AnthropicProvider()
    if name == "openai":
        from app.llm.hosted import OpenAIProvider

        return OpenAIProvider()
    raise ValueError(
        f"unknown BRIEFLY_LLM_PROVIDER {name!r}; expected rule_based, anthropic or openai"
    )


def available_providers() -> list[str]:
    return sorted({"rule_based", "anthropic", "openai", *_REGISTRY})
