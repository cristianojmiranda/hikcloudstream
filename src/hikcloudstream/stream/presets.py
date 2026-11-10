"""Use existing PTZ presets for zone capture with an explicit return position."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from hikcloudstream.client import HikConnectClient
from hikcloudstream.exceptions import PTZRestoreError
from hikcloudstream.models import Camera, StreamType
from hikcloudstream.stream.session import capture_live_snapshot
from hikcloudstream.stream.zone import Zone, capture_zone_snapshot, record_zone_stream


@contextmanager
def preset_zone(
    client: HikConnectClient,
    camera: Camera,
    *,
    zone_preset: int,
    home_preset: int,
    settle_seconds: float = 5.0,
) -> Iterator[None]:
    """Aim at a preset and always command a return to the selected home preset."""
    if zone_preset < 1 or home_preset < 1 or zone_preset == home_preset:
        raise ValueError("zone and home presets must be distinct positive indices")
    if settle_seconds < 0:
        raise ValueError("settle_seconds must not be negative")
    try:
        client.goto_preset(camera, zone_preset)
        time.sleep(settle_seconds)
        yield
    finally:
        for attempt in range(3):
            try:
                client.goto_preset(camera, home_preset)
                break
            except Exception as exc:
                if attempt == 2:
                    raise PTZRestoreError(
                        "could not return camera to home preset after three attempts"
                    ) from exc
                time.sleep(1.0)


def capture_preset_snapshot(
    client: HikConnectClient,
    camera: Camera,
    output_path: Path,
    *,
    zone_preset: int,
    home_preset: int,
    settle_seconds: float = 5.0,
    zone: Zone | None = None,
    warmup_seconds: float = 15.0,
    ffmpeg_path: str = "ffmpeg",
    validate_code: str | None = None,
    stream_type: StreamType | int | None = StreamType.AUTO,
) -> Path:
    """Capture a frame at a saved PTZ position and then recall home."""
    with preset_zone(
        client, camera, zone_preset=zone_preset,
        home_preset=home_preset, settle_seconds=settle_seconds,
    ):
        capture = capture_zone_snapshot if zone else capture_live_snapshot
        kwargs = {"zone": zone} if zone else {}
        return capture(
            client, camera, output_path, **kwargs,
            warmup_seconds=warmup_seconds,
            ffmpeg_path=ffmpeg_path,
            validate_code=validate_code,
            stream_type=stream_type,
        )


def record_preset_stream(
    client: HikConnectClient,
    camera: Camera,
    output_path: Path,
    *,
    zone_preset: int,
    home_preset: int,
    settle_seconds: float = 5.0,
    zone: Zone | None = None,
    duration_seconds: float = 10.0,
    ffmpeg_path: str = "ffmpeg",
    validate_code: str | None = None,
    stream_type: StreamType | int | None = StreamType.AUTO,
) -> Path:
    """Record at a saved PTZ position and then recall home."""
    with preset_zone(
        client, camera, zone_preset=zone_preset,
        home_preset=home_preset, settle_seconds=settle_seconds,
    ):
        return record_zone_stream(
            client, camera, output_path, zone or Zone(0, 0, 1, 1),
            duration_seconds=duration_seconds,
            ffmpeg_path=ffmpeg_path,
            validate_code=validate_code,
            stream_type=stream_type,
        )
