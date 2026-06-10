"""Stream type auto-detection (substream vs main)."""

from __future__ import annotations

import re

from pyezvizapi.exceptions import PyEzvizError
from pyezvizapi.stream import VtmChannel, VtmStreamClient, rtp_payload

from hikcloudstream._config import STREAM_PROBE_TIMEOUT
from hikcloudstream.client import HikConnectClient
from hikcloudstream.models import Camera
from hikcloudstream.stream.adapter import HikConnectStreamAdapter


def with_stream_type(stream_url: str, stream_type: int) -> str:
    if f"stream={stream_type}" in stream_url:
        return stream_url
    if "stream=" in stream_url:
        return re.sub(r"stream=\d+", f"stream={stream_type}", stream_url, count=1)
    separator = "&" if "?" in stream_url else "?"
    return f"{stream_url}{separator}stream={stream_type}"


def substream_has_media(stream_url: str, *, timeout: float) -> bool:
    try:
        with VtmStreamClient(stream_url, timeout=timeout) as stream:
            stream.start()
            for packet in stream.iter_packets(max_packets=40):
                if packet.channel not in (VtmChannel.STREAM, VtmChannel.ENCRYPTED_STREAM):
                    continue
                if not packet.body:
                    continue
                payload = rtp_payload(packet.body)
                if len(payload) > 8:
                    return True
    except (TimeoutError, OSError, PyEzvizError):
        return False
    return False


def resolve_stream_type(
    client: HikConnectClient,
    camera: Camera,
    *,
    client_type: int = 55,
    probe_timeout: float = STREAM_PROBE_TIMEOUT,
) -> int:
    """Prefer substream (2); fall back to main (1) when unavailable."""
    from hikcloudstream.stream.session import build_cloud_stream_info

    adapter = HikConnectStreamAdapter(client)
    substream_info = build_cloud_stream_info(
        adapter,
        camera,
        client_type=client_type,
        refresh_vtm=True,
        stream_type=2,
    )
    if substream_has_media(substream_info["stream_url"], timeout=probe_timeout):
        return 2
    return 1
