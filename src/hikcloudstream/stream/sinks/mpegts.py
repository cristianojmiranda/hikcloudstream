"""FFmpeg MPEG-TS remux sinks."""

from __future__ import annotations

import io
import subprocess
import threading
from typing import BinaryIO

from pyezvizapi.stream import StreamTransport, VtmStreamClient

from hikcloudstream.exceptions import FFmpegNotFoundError, StreamNegotiationError
from hikcloudstream.stream.sinks.annex_b import iter_annex_b_chunks, write_stream_payloads


def ffmpeg_input_format(transport: StreamTransport) -> str:
    if transport == StreamTransport.MPEG_PS:
        return "mpeg"
    return "h264"


def open_mpegts_remux_process(
    ffmpeg_path: str,
    *,
    input_format: str = "h264",
) -> subprocess.Popen[bytes]:
    try:
        return subprocess.Popen(
            [
                ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-fflags",
                "nobuffer",
                "-flags",
                "low_delay",
                "-f",
                input_format,
                "-i",
                "pipe:0",
                "-c",
                "copy",
                "-f",
                "mpegts",
                "pipe:1",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise FFmpegNotFoundError(f"could not launch FFmpeg at {ffmpeg_path!r}: {exc}") from exc


def remux_annex_b_to_mpegts(
    payload: bytes,
    output: BinaryIO,
    *,
    ffmpeg_path: str,
    transport: StreamTransport,
) -> None:
    if not payload:
        raise StreamNegotiationError("live stream returned no media packets")
    process = open_mpegts_remux_process(
        ffmpeg_path,
        input_format=ffmpeg_input_format(transport),
    )
    try:
        remuxed, _stderr = process.communicate(payload)
        if process.returncode != 0:
            raise FFmpegNotFoundError(f"FFmpeg remux failed with exit code {process.returncode}")
        output.write(remuxed)
        output.flush()
    finally:
        if process.poll() is None:
            process.kill()


def remux_stream_incremental(
    stream: VtmStreamClient,
    output: BinaryIO,
    *,
    ffmpeg_path: str,
    max_packets: int | None = None,
    duration_seconds: float | None = None,
) -> None:
    chunk_iter = iter_annex_b_chunks(
        stream,
        max_packets=max_packets,
        duration_seconds=duration_seconds,
    )
    try:
        transport, first_chunk = next(chunk_iter)
    except StopIteration as exc:
        raise StreamNegotiationError("live stream returned no media packets") from exc

    process = open_mpegts_remux_process(
        ffmpeg_path,
        input_format=ffmpeg_input_format(transport),
    )
    stdin = process.stdin
    stdout = process.stdout
    if stdin is None or stdout is None:
        raise FFmpegNotFoundError("could not open FFmpeg pipes")

    writer_error: list[Exception] = []

    def _feed_ffmpeg() -> None:
        try:
            stdin.write(first_chunk)
            for _transport, chunk in chunk_iter:
                stdin.write(chunk)
        except Exception as exc:
            writer_error.append(exc)
        finally:
            stdin.close()

    feeder = threading.Thread(target=_feed_ffmpeg, daemon=True)
    feeder.start()

    while True:
        chunk = stdout.read(65536)
        if not chunk:
            break
        output.write(chunk)

    feeder.join()
    process.wait()
    if writer_error:
        raise writer_error[0]
    if process.returncode not in (0, None):
        raise FFmpegNotFoundError(f"FFmpeg remux failed with exit code {process.returncode}")


def remux_stream_to_mpegts(
    stream: VtmStreamClient,
    output: BinaryIO,
    *,
    ffmpeg_path: str,
    max_packets: int | None = None,
    duration_seconds: float | None = None,
    live: bool = False,
) -> None:
    if live:
        remux_stream_incremental(
            stream,
            output,
            ffmpeg_path=ffmpeg_path,
            max_packets=max_packets,
            duration_seconds=duration_seconds,
        )
        return

    buffer = io.BytesIO()
    transport = write_stream_payloads(
        stream,
        buffer,
        max_packets=max_packets,
        duration_seconds=duration_seconds,
    )
    remux_annex_b_to_mpegts(
        buffer.getvalue(),
        output,
        ffmpeg_path=ffmpeg_path,
        transport=transport,
    )
