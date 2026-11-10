"""Capture a selected area of the live image without changing camera position."""

from __future__ import annotations

import io
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from hikcloudstream.client import HikConnectClient
from hikcloudstream.exceptions import FFmpegNotFoundError
from hikcloudstream.models import Camera, StreamType
from hikcloudstream.stream.session import capture_live_snapshot, record_stream, require_ffmpeg


@dataclass(frozen=True)
class Zone:
    """A rectangle in normalized full-frame coordinates."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if not (
            0 <= self.x < 1
            and 0 <= self.y < 1
            and 0 < self.width <= 1
            and 0 < self.height <= 1
            and self.x + self.width <= 1
            and self.y + self.height <= 1
        ):
            raise ValueError("zone must fit inside the image, with positive width and height")

    @classmethod
    def parse(cls, value: str) -> Zone:
        try:
            parts = [float(item.strip()) for item in value.split(",")]
            if len(parts) != 4:
                raise ValueError
            return cls(*parts)
        except (TypeError, ValueError) as exc:
            raise ValueError("zone must be x,y,width,height with values from 0 to 1") from exc


def crop_jpeg(image_bytes: bytes, zone: Zone) -> bytes:
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as image:
        left = round(image.width * zone.x)
        top = round(image.height * zone.y)
        right = round(image.width * (zone.x + zone.width))
        bottom = round(image.height * (zone.y + zone.height))
        cropped = image.crop((left, top, right, bottom))
        output = io.BytesIO()
        cropped.save(output, format="JPEG", quality=90)
        return output.getvalue()


def capture_zone_snapshot(
    client: HikConnectClient,
    camera: Camera,
    output_path: Path,
    zone: Zone,
    *,
    warmup_seconds: float = 15.0,
    ffmpeg_path: str = "ffmpeg",
    validate_code: str | None = None,
    stream_type: StreamType | int | None = StreamType.AUTO,
) -> Path:
    """Save one cropped frame from the live stream; camera orientation is unchanged."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hikcloudstream-zone-", dir=output_path.parent) as tmp:
        full_path = Path(tmp) / "full.jpg"
        capture_live_snapshot(
            client,
            camera,
            full_path,
            warmup_seconds=warmup_seconds,
            ffmpeg_path=ffmpeg_path,
            validate_code=validate_code,
            stream_type=stream_type,
        )
        cropped = crop_jpeg(full_path.read_bytes(), zone)
        staged = Path(tmp) / "zone.jpg"
        staged.write_bytes(cropped)
        staged.replace(output_path)
    return output_path


def record_zone_stream(
    client: HikConnectClient,
    camera: Camera,
    output_path: Path,
    zone: Zone,
    *,
    duration_seconds: float = 10.0,
    ffmpeg_path: str = "ffmpeg",
    validate_code: str | None = None,
    stream_type: StreamType | int | None = StreamType.AUTO,
) -> Path:
    """Record a cropped live image to H.264 MPEG-TS without moving the camera."""
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than zero")
    ffmpeg = require_ffmpeg(ffmpeg_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hikcloudstream-zone-", dir=output_path.parent) as tmp:
        full_path = Path(tmp) / "full.ts"
        staged = Path(tmp) / "zone.ts"
        record_stream(
            client,
            camera,
            full_path,
            duration_seconds=duration_seconds + 15.0,
            ffmpeg_path=ffmpeg,
            validate_code=validate_code,
            stream_type=stream_type,
        )
        filter_expr = (
            f"crop=trunc(iw*{zone.width}/2)*2:trunc(ih*{zone.height}/2)*2:"
            f"trunc(iw*{zone.x}/2)*2:trunc(ih*{zone.y}/2)*2"
        )
        result = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(full_path), "-t", str(duration_seconds), "-vf", filter_expr,
                "-c:v", "libx264", "-preset", "veryfast", "-an",
                "-f", "mpegts", str(staged),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not staged.is_file() or staged.stat().st_size == 0:
            raise FFmpegNotFoundError("FFmpeg could not encode the selected video zone")
        staged.replace(output_path)
    return output_path
