"""Choose the configured TTS provider."""

from __future__ import annotations

from app.config import get_settings
from app.tts.base import TTSProvider
from app.tts.providers import (
    AzureSpeechProvider,
    ElevenLabsProvider,
    LocalTTSProvider,
    OpenAITTSProvider,
)

_PROVIDERS: dict[str, type[TTSProvider]] = {
    "local": LocalTTSProvider,
    "elevenlabs": ElevenLabsProvider,
    "openai": OpenAITTSProvider,
    "azure": AzureSpeechProvider,
}


def register(name: str, cls: type[TTSProvider]) -> None:
    _PROVIDERS[name] = cls


def get_tts_provider(name: str | None = None) -> TTSProvider:
    settings = get_settings()
    key = (name or settings.tts_provider or "local").lower()
    if key not in _PROVIDERS:
        raise ValueError(
            f"unknown BRIEFLY_TTS_PROVIDER {key!r}; expected one of {sorted(_PROVIDERS)}"
        )
    return _PROVIDERS[key]()


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)
