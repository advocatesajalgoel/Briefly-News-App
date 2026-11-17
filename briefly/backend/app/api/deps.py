"""Shared dependencies: auth and pagination."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings
from app.db import get_db

__all__ = ["get_db", "require_admin", "require_client", "encode_cursor", "decode_cursor"]


def require_admin(
    x_admin_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.admin_token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Admin endpoints are disabled because BRIEFLY_ADMIN_TOKEN is not set.",
        )
    if not x_admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid admin token.")


def require_client(
    x_briefly_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Optional shared key for the read API.

    Left blank by default: these endpoints serve public headlines and links to
    material that is already public, so gating them buys little. Set
    ``BRIEFLY_CLIENT_API_KEY`` if you would rather they were closed.
    """
    if not settings.client_api_key:
        return
    if x_briefly_key != settings.client_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid client key.")


def encode_cursor(payload: dict) -> str:
    raw = json.dumps(payload, default=str).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> dict | None:
    if not cursor:
        return None
    try:
        padding = "=" * (-len(cursor) % 4)
        return json.loads(base64.urlsafe_b64decode(cursor + padding))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed cursor.") from None


def parse_cursor_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed cursor.") from None
