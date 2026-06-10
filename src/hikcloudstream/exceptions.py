"""Typed exceptions for the Hik-Connect cloud API and streaming layer."""

from __future__ import annotations


class HikCloudStreamError(Exception):
    """Base exception for all library errors."""


class AuthenticationError(HikCloudStreamError):
    """Login or session authentication failed."""


class CaptchaRequiredError(AuthenticationError):
    """Account requires CAPTCHA — log in via the official app first."""


class ApiError(HikCloudStreamError):
    """REST API returned an error response."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"API error {code}: {message}")


class CameraNotFoundError(HikCloudStreamError):
    """Requested camera index is out of range."""


class StreamNegotiationError(HikCloudStreamError):
    """VTM stream session negotiation failed."""


class TokenError(HikCloudStreamError):
    """VTDU stream token could not be obtained."""


class EncryptedStreamError(HikCloudStreamError):
    """Stream requires encryption key not provided or not supported."""


class CaptureError(HikCloudStreamError):
    """Cloud snapshot capture or decrypt failed."""


class FFmpegNotFoundError(HikCloudStreamError):
    """FFmpeg executable is not available on PATH."""
