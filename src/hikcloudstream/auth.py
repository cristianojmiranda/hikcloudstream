"""Authentication helpers and API response validation."""

from __future__ import annotations

from typing import Any

from hikcloudstream.exceptions import ApiError, AuthenticationError, CaptchaRequiredError


def check_api_meta(payload: dict[str, Any]) -> None:
    """Raise typed errors when the Hik-Connect meta block indicates failure."""
    meta = payload.get("meta") or {}
    code = meta.get("code", 0)
    if code == 200:
        return
    message = str(meta.get("message") or meta.get("langMsg") or "unknown error")
    raise ApiError(int(code), message)


def raise_login_error(payload: dict[str, Any]) -> None:
    """Map login response codes to typed authentication errors."""
    meta = payload.get("meta") or {}
    code = meta.get("code")
    if code in (1013, 1014):
        raise AuthenticationError("invalid username or password")
    if code == 1015:
        raise CaptchaRequiredError(
            "CAPTCHA required — log in once via the Hik-Connect app, then retry"
        )
    check_api_meta(payload)
