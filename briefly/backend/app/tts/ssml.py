"""Minimal SSML wrapping for providers that accept it."""

from __future__ import annotations

from xml.sax.saxutils import escape


def to_ssml(text: str, *, voice: str = "en-IN-NeerjaNeural", rate: float = 1.0,
            lang: str = "en-IN") -> str:
    paragraphs = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    body = "".join(f"<p>{escape(p)}</p><break time=\"420ms\"/>" for p in paragraphs)
    percent = int(round((rate - 1.0) * 100))
    prosody_rate = f"{percent:+d}%" if percent else "0%"
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang}">'
        f'<voice name="{voice}"><prosody rate="{prosody_rate}">{body}</prosody></voice></speak>'
    )
