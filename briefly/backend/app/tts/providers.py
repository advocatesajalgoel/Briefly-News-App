"""Concrete TTS providers.

``local``      espeak-ng on the host — no credentials, real speech, useful for
               development and for keeping the pipeline testable end to end.
``elevenlabs`` / ``openai`` / ``azure`` — hosted voices. Each reads its key from
               the environment and degrades to ``local`` when the key is absent,
               so a missing credential never stops an episode being produced.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.tts.base import (
    MIME_TYPES,
    SynthesisRequest,
    SynthesisResult,
    TTSProvider,
    TTSUnavailable,
    probe_duration_seconds,
    strip_markup,
    transcode,
    wav_silence,
)

WORDS_PER_MINUTE = 150


def _estimate_seconds(text: str) -> int:
    words = len(strip_markup(text).split())
    return max(1, int(round(words / WORDS_PER_MINUTE * 60)))


class LocalTTSProvider(TTSProvider):
    """espeak-ng, with a silent-WAV fallback if it is not installed."""

    name = "local"

    def available(self) -> bool:
        return True

    def _espeak(self) -> str | None:
        return shutil.which("espeak-ng") or shutil.which("espeak")

    def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
        text = strip_markup(request.text)
        warnings: list[str] = []
        fmt = request.fmt or "mp3"
        binary = self._espeak()

        if binary:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "speech.wav"
                words_per_minute = int(WORDS_PER_MINUTE * max(0.5, min(2.0, request.speaking_rate)))
                proc = subprocess.run(
                    [binary, "-v", "en-gb", "-s", str(words_per_minute), "-w", str(out), "--stdin"],
                    input=text.encode("utf-8"),
                    capture_output=True,
                )
                if proc.returncode == 0 and out.exists() and out.stat().st_size > 44:
                    wav = out.read_bytes()
                else:  # pragma: no cover - depends on host
                    wav = wav_silence(_estimate_seconds(text))
                    warnings.append("espeak-ng failed; produced silent placeholder audio")
        else:
            wav = wav_silence(_estimate_seconds(text))
            warnings.append(
                "espeak-ng is not installed; produced silent placeholder audio. "
                "Install espeak-ng, or configure a hosted TTS provider."
            )

        try:
            audio = transcode(wav, "wav", fmt)
        except TTSUnavailable as exc:
            audio, fmt = wav, "wav"
            warnings.append(str(exc))

        duration = probe_duration_seconds(audio, fmt) or _estimate_seconds(text)
        return SynthesisResult(
            audio=audio,
            fmt=fmt,
            mime_type=MIME_TYPES.get(fmt, "application/octet-stream"),
            duration_seconds=duration,
            provider=self.name,
            voice=request.voice,
            warnings=warnings,
        )


class _HostedTTS(TTSProvider):
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.settings = get_settings()
        self._client = client
        self._fallback = LocalTTSProvider()

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=120.0)
        return self._client

    def _degrade(self, request: SynthesisRequest, reason: str) -> SynthesisResult:
        result = self._fallback.synthesise(request)
        result.warnings.insert(0, f"{self.name} unavailable ({reason}); used local TTS")
        return result


class ElevenLabsProvider(_HostedTTS):
    name = "elevenlabs"

    def available(self) -> bool:
        return bool(self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15), reraise=True)
    def _post(self, text: str) -> bytes:
        voice_id = self.settings.elevenlabs_voice_id
        resp = self._http().post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": self.settings.elevenlabs_api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
        )
        resp.raise_for_status()
        return resp.content

    def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
        if not self.available():
            return self._degrade(request, "ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID not set")
        try:
            mp3 = self._post(strip_markup(request.text))
        except Exception as exc:
            return self._degrade(request, f"{type(exc).__name__}: {exc}")
        fmt = request.fmt or "mp3"
        audio = mp3 if fmt == "mp3" else transcode(mp3, "mp3", fmt)
        return SynthesisResult(
            audio=audio,
            fmt=fmt,
            mime_type=MIME_TYPES.get(fmt, "audio/mpeg"),
            duration_seconds=probe_duration_seconds(audio, fmt) or _estimate_seconds(request.text),
            provider=self.name,
            voice=self.settings.elevenlabs_voice_id,
        )


class OpenAITTSProvider(_HostedTTS):
    name = "openai"

    def available(self) -> bool:
        return bool(self.settings.openai_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15), reraise=True)
    def _post(self, text: str, voice: str) -> bytes:
        resp = self._http().post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.openai_tts_model,
                "voice": voice,
                "input": text,
                "response_format": "mp3",
            },
        )
        resp.raise_for_status()
        return resp.content

    def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
        if not self.available():
            return self._degrade(request, "OPENAI_API_KEY not set")
        # The hosted catalogue uses its own voice names; "briefly-anchor" is our
        # internal label, so map anything unrecognised to a neutral default.
        voice = request.voice if request.voice and "-" not in request.voice else "alloy"
        try:
            mp3 = self._post(strip_markup(request.text), voice)
        except Exception as exc:
            return self._degrade(request, f"{type(exc).__name__}: {exc}")
        fmt = request.fmt or "mp3"
        audio = mp3 if fmt == "mp3" else transcode(mp3, "mp3", fmt)
        return SynthesisResult(
            audio=audio,
            fmt=fmt,
            mime_type=MIME_TYPES.get(fmt, "audio/mpeg"),
            duration_seconds=probe_duration_seconds(audio, fmt) or _estimate_seconds(request.text),
            provider=self.name,
            voice=voice,
        )


class AzureSpeechProvider(_HostedTTS):
    name = "azure"

    def available(self) -> bool:
        return bool(self.settings.azure_speech_key and self.settings.azure_speech_region)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15), reraise=True)
    def _post(self, ssml: str) -> bytes:
        region = self.settings.azure_speech_region
        resp = self._http().post(
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={
                "Ocp-Apim-Subscription-Key": self.settings.azure_speech_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                "User-Agent": "Briefly",
            },
            content=ssml.encode("utf-8"),
        )
        resp.raise_for_status()
        return resp.content

    def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
        if not self.available():
            return self._degrade(request, "AZURE_SPEECH_KEY or AZURE_SPEECH_REGION not set")
        from app.tts.ssml import to_ssml

        voice = request.voice if "-" in (request.voice or "") else "en-IN-NeerjaNeural"
        try:
            mp3 = self._post(to_ssml(request.text, voice=voice, rate=request.speaking_rate))
        except Exception as exc:
            return self._degrade(request, f"{type(exc).__name__}: {exc}")
        fmt = request.fmt or "mp3"
        audio = mp3 if fmt == "mp3" else transcode(mp3, "mp3", fmt)
        return SynthesisResult(
            audio=audio,
            fmt=fmt,
            mime_type=MIME_TYPES.get(fmt, "audio/mpeg"),
            duration_seconds=probe_duration_seconds(audio, fmt) or _estimate_seconds(request.text),
            provider=self.name,
            voice=voice,
        )
