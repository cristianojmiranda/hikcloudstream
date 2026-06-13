"""PyAV MJPEG frame sink."""

from __future__ import annotations

import io
import time
from typing import Any, BinaryIO

from pyezvizapi.stream import VtmStreamClient

from hikcloudstream._config import MJPEG_BOUNDARY
from hikcloudstream.exceptions import EncryptedStreamError
from hikcloudstream.stream.sinks.annex_b import iter_annex_b_chunks


def placeholder_jpeg(message: str) -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (640, 360), color=(20, 20, 20))
    draw = ImageDraw.Draw(image)
    wrapped: list[str] = []
    line = ""
    for word in message.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) > 42:
            if line:
                wrapped.append(line)
            line = word
        else:
            line = candidate
    if line:
        wrapped.append(line)
    y = 150 - (len(wrapped) * 12)
    for text_line in wrapped:
        draw.text((24, y), text_line, fill=(230, 230, 230))
        y += 24
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def av_frame_to_jpeg(
    frame: Any,
    *,
    quality: int = 82,
    max_width: int | None = 1280,
) -> bytes:
    if max_width and frame.width > max_width:
        height = max(2, int(frame.height * max_width / frame.width) // 2 * 2)
        frame = frame.reformat(width=max_width, height=height)
    buffer = io.BytesIO()
    save_kw: dict = {"format": "JPEG", "quality": quality}
    if quality >= 90:
        save_kw["optimize"] = False
        save_kw["subsampling"] = 0
    else:
        save_kw["optimize"] = True
    frame.to_image().save(buffer, **save_kw)
    return buffer.getvalue()


def write_mjpeg_frame(output: BinaryIO, frame: bytes) -> None:
    output.write(b"--" + MJPEG_BOUNDARY + b"\r\n")
    output.write(b"Content-Type: image/jpeg\r\n")
    output.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
    output.write(frame)
    output.write(b"\r\n")
    output.flush()


def stream_mjpeg(
    stream: VtmStreamClient,
    output: BinaryIO,
    *,
    frame_fps: float = 4.0,
    validate_code: str | None = None,
    stream_type: int = 2,
    jpeg_quality: int = 82,
    max_width: int | None = None,
    require_keyframe: bool = True,
) -> None:
    """Stream MJPEG via PyAV — continuous H.264 decoder."""
    import av

    if validate_code:
        raise EncryptedStreamError(
            "encrypted live streams are not supported in the MJPEG viewer yet; "
            "use validate_code with record_to_file or capture_frame only"
        )

    codec = av.CodecContext.create("h264", "r")
    frame_period = 1.0 / frame_fps
    next_emit = 0.0
    started_at = time.monotonic()
    sent_placeholder = False
    if max_width is None:
        max_width = 1920 if stream_type == 1 else 1408
    quality = max(50, min(jpeg_quality, 95))
    got_keyframe = not require_keyframe
    keyframe_deadline = started_at + 3.0 if require_keyframe else 0.0

    try:
        chunk_iter = iter_annex_b_chunks(stream)
        while True:
            try:
                _transport, chunk = next(chunk_iter)
            except StopIteration:
                return
            except OSError:
                return

            try:
                packets = codec.parse(chunk)
            except av.error.InvalidDataError:
                continue

            for packet in packets:
                try:
                    decoded_frames = codec.decode(packet)
                except av.error.InvalidDataError:
                    continue

                for frame in decoded_frames:
                    if not got_keyframe:
                        if getattr(frame, "key_frame", False):
                            got_keyframe = True
                        elif time.monotonic() < keyframe_deadline:
                            continue
                        else:
                            got_keyframe = True
                    now = time.monotonic()
                    if now < next_emit:
                        continue
                    next_emit = now + frame_period
                    try:
                        jpeg = av_frame_to_jpeg(
                            frame, max_width=max_width, quality=quality
                        )
                    except Exception:
                        continue
                    write_mjpeg_frame(output, jpeg)
                    sent_placeholder = True

            if not sent_placeholder and time.monotonic() - started_at > 2.0:
                write_mjpeg_frame(output, placeholder_jpeg("Waiting for video..."))
                sent_placeholder = True
    except (BrokenPipeError, ConnectionResetError):
        return
