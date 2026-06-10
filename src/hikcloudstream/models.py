"""Public data models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class StreamType(IntEnum):
    """VTM live stream profile (stream= query parameter)."""

    AUTO = 0
    MAIN = 1
    SUB = 2


@dataclass(frozen=True)
class Credentials:
    """Hik-Connect account credentials."""

    username: str
    password: str


@dataclass(frozen=True)
class ClientConfig:
    """HTTP client identity and connection settings."""

    api_base_url: str = "https://api.hik-connect.com"
    client_type: str = "55"
    client_version: str = "6.0.0.20250101"
    locale: str = "en-US"
    client_no: str = "hikcloudstream"
    client_name: str = "hikcloudstream"
    os_version: str = "Linux"
    net_type: str = "WIFI"
    timeout: float = 30.0


@dataclass(frozen=True)
class Camera:
    """A camera channel visible on the Hik-Connect account."""

    index: int
    name: str
    device_serial: str
    channel_no: int
    device_name: str
