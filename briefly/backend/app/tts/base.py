"""TTS provider interface and shared audio helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

MIME_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "opus": "audio/opus",
}


@dataclass
class SynthesisRequest:
    text: str
    voice: str = "briefly-anchor"
    fmt: str = "mp3"
    speaking_rate: float = 1.0
    # Optional per-segment breaks so the player can show chapter positions.
    segment_texts: list[str] = field(default_factory=list)


@dataclass
class SynthesisResult:
    audio: bytes
    fmt: str
    mime_type: str
    duration_seconds: int
    provider: str
    voice: str
    warnings: list[str] = field(default_factory=list)

    @property
    def size_bytes(self) -> int:
        return len(self.audio)


class TTSProvider:
    name = "base"

    def available(self) -> bool:
        return False

    def synthesise(self, request: SynthesisRequest) -> SynthesisResult:  # pragma: no cover
        raise NotImplementedError


class TTSUnavailable(RuntimeError):
    pass


# --- shared helpers ---------------------------------------------------------

_SSML_TAG = re.compile(r"<[^>]+>")


def strip_markup(text: str) -> str:
    return _SSML_TAG.sub(" ", text or "").replace(" ", " ").strip()


def ffmpeg_path() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:  # the imageio wheel bundles a static build
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def speech_bitrate() -> str:
    """Encoding rate for narration, from settings, with a sane fallback."""
    try:
        from app.config import get_settings

        return get_settings().tts_bitrate or "48k"
    except Exception:
        return "48k"


def transcode(data: bytes, src_fmt: str, dst_fmt: str) -> bytes:
    """Convert audio between containers using ffmpeg when it is available."""
    if src_fmt == dst_fmt:
        return data
    binary = ffmpeg_path()
    if not binary:
        raise TTSUnavailable(
            f"cannot convert {src_fmt} to {dst_fmt}: ffmpeg is not installed. "
            f"Install ffmpeg or set BRIEFLY_TTS_FORMAT={src_fmt}."
        )
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in.{src_fmt}"
        dst = Path(tmp) / f"out.{dst_fmt}"
        src.write_bytes(data)
        rate = speech_bitrate()
        codec = {"mp3": ["-codec:a", "libmp3lame", "-b:a", rate],
                 "m4a": ["-codec:a", "aac", "-b:a", rate],
                 "aac": ["-codec:a", "aac", "-b:a", rate],
                 "opus": ["-codec:a", "libopus", "-b:a", rate],
                 "wav": []}.get(dst_fmt, [])
        # One narrator, no music: mono at 22.05 kHz loses nothing audible.
        shape = [] if dst_fmt == "wav" else ["-ac", "1", "-ar", "22050"]
        proc = subprocess.run(
            [binary, "-y", "-loglevel", "error", "-i", str(src),
             *shape, *codec, str(dst)],
            capture_output=True,
        )
        if proc.returncode != 0 or not dst.exists():
            raise TTSUnavailable(
                f"ffmpeg failed converting {src_fmt}->{dst_fmt}: "
                f"{proc.stderr.decode('utf-8', 'ignore')[:300]}"
            )
        return dst.read_bytes()


def probe_duration_seconds(data: bytes, fmt: str) -> int | None:
    binary = ffmpeg_path()
    if not binary:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"probe.{fmt}"
        path.write_bytes(data)
        proc = subprocess.run(
            [binary, "-i", str(path), "-f", "null", "-"], capture_output=True
        )
        text = proc.stderr.decode("utf-8", "ignore")
        match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", text)
        if not match:
            return None
        h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
        return int(h * 3600 + m * 60 + s)


def wav_silence(seconds: int, sample_rate: int = 22050) -> bytes:
    """A valid, silent WAV. Last-resort placeholder so playback still works."""
    import struct

    frames = max(1, int(seconds * sample_rate))
    data_size = frames * 2
    header = b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", data_size)
    return header + b"\x00\x00" * frames
