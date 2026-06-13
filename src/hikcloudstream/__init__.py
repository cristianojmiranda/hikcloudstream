"""Unofficial Python SDK for Hik-Connect cloud cameras."""

from hikcloudstream._config import CLOUD_CAPTURE_MAX
from hikcloudstream.client import HikConnectClient
from hikcloudstream.exceptions import (
    ApiError,
    AuthenticationError,
    CameraNotFoundError,
    CaptchaRequiredError,
    CaptureError,
    EncryptedStreamError,
    FFmpegNotFoundError,
    HikCloudStreamError,
    StreamNegotiationError,
    TokenError,
)
from hikcloudstream.models import Camera, ClientConfig, Credentials, StreamType

__version__ = "0.1.2"

__all__ = [
    "CLOUD_CAPTURE_MAX",
    "ApiError",
    "AuthenticationError",
    "Camera",
    "CameraNotFoundError",
    "CaptchaRequiredError",
    "CaptureError",
    "ClientConfig",
    "Credentials",
    "EncryptedStreamError",
    "FFmpegNotFoundError",
    "HikCloudStreamError",
    "HikConnectClient",
    "StreamNegotiationError",
    "StreamType",
    "TokenError",
    "__version__",
]
