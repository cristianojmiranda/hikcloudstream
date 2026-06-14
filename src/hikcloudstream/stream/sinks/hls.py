"""FFmpeg HLS fMP4 remux sink — H.264 passthrough from VTM Annex B."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from pyezvizapi.stream import VtmStreamClient

from hikcloudstream.exceptions import FFmpegNotFoundError, StreamNegotiationError
from hikcloudstream.stream.sinks.annex_b import iter_annex_b_chunks
from hikcloudstream.stream.sinks.mpegts import ffmpeg_input_format


def prepare_hls_output_dir(output_dir: Path) -> None:
    """Remove prior segments and create a clean HLS output directory."""
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def open_hls_remux_process(
    output_dir: Path,
    ffmpeg_path: str = "ffmpeg",
    *,
    segment_seconds: float = 2.0,
    list_size: int = 6,
    input_format: str = "h264",
) -> subprocess.Popen[bytes]:
    playlist = output_dir / "index.m3u8"
    segment_pattern = str(output_dir / "seg_%05d.m4s")
    try:
        return subprocess.Popen(
            [
                ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-fflags",
                "+genpts+igndts+nobuffer",
                "-use_wallclock_as_timestamps",
                "1",
                "-probesize",
                "500000",
                "-analyzeduration",
                "1000000",
                "-flags",
                "low_delay",
                "-f",
                input_format,
                "-i",
                "pipe:0",
                "-c",
                "copy",
                "-f",
                "hls",
                "-hls_time",
                str(max(segment_seconds, 1.0)),
                "-hls_list_size",
                str(max(list_size, 3)),
                "-hls_flags",
                "delete_segments+append_list+independent_segments+omit_endlist",
                "-hls_segment_type",
                "fmp4",
                "-hls_fmp4_init_filename",
                "init.mp4",
                "-hls_segment_filename",
                segment_pattern,
                str(playlist),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise FFmpegNotFoundError(f"could not launch FFmpeg at {ffmpeg_path!r}: {exc}") from exc


def _read_ffmpeg_stderr(process: subprocess.Popen[bytes]) -> str:
    stderr = process.stderr
    if stderr is None:
        return ""
    try:
        return stderr.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


class _SegmentWatcher:
    """O(1) segment detection — checks expected seq files, no directory glob."""

    _SCAN_AHEAD = 12

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._highest_seq = 0
        self._segments_emitted = 0

    def poll(self) -> list[int]:
        """Return cumulative counts for each newly observed segment (may be >1 per poll)."""
        new_counts: list[int] = []
        limit = self._highest_seq + self._SCAN_AHEAD
        seq = self._highest_seq + 1
        while seq <= limit:
            if (self._output_dir / f"seg_{seq:05d}.m4s").is_file():
                self._highest_seq = seq
                self._segments_emitted += 1
                new_counts.append(self._segments_emitted)
            seq += 1
        return new_counts


def hls_output_ready(output_dir: Path) -> bool:
    if not (output_dir / "index.m3u8").is_file():
        return False
    if (output_dir / "init.mp4").is_file():
        return True
    return any(output_dir.glob("seg_*.m4s"))


def wait_for_hls_ready(
    output_dir: Path,
    *,
    timeout: float = 20.0,
    ingest_thread: threading.Thread | None = None,
    errors: list[str] | None = None,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if hls_output_ready(output_dir):
            return True
        if ingest_thread is not None and not ingest_thread.is_alive() and errors:
            return False
        time.sleep(0.25)
    return False


def hls_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".m3u8":
        return "application/vnd.apple.mpegurl"
    if suffix == ".m4s":
        return "video/iso.segment"
    if suffix == ".mp4":
        return "video/mp4"
    return "application/octet-stream"


def stream_annex_b_to_hls(
    stream: VtmStreamClient,
    output_dir: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
    segment_seconds: float = 2.0,
    list_size: int = 6,
    stop_event: threading.Event | None = None,
    on_segment: Callable[[int], None] | None = None,
    progress_interval_seconds: float = 0.25,
) -> None:
    """
    Feed live Annex B H.264 into ffmpeg and write rolling HLS fMP4 segments.

    ``on_segment`` is called with the current segment count when a new ``.m4s``
    file appears (used by GATO to signal readiness and health ticks).
    """
    prepare_hls_output_dir(output_dir)
    chunk_iter = iter_annex_b_chunks(stream)
    try:
        transport, first_chunk = next(chunk_iter)
    except StopIteration as exc:
        raise StreamNegotiationError("live stream returned no media packets") from exc

    process = open_hls_remux_process(
        output_dir,
        ffmpeg_path,
        segment_seconds=segment_seconds,
        list_size=list_size,
        input_format=ffmpeg_input_format(transport),
    )
    stdin = process.stdin
    if stdin is None:
        raise FFmpegNotFoundError("could not open FFmpeg stdin pipe")

    writer_error: list[Exception] = []
    segment_watcher = _SegmentWatcher(output_dir)
    last_progress_at = 0.0

    def _maybe_notify_progress(force: bool = False) -> None:
        nonlocal last_progress_at
        if on_segment is None:
            return
        now = time.monotonic()
        if not force and now - last_progress_at < progress_interval_seconds:
            return
        last_progress_at = now
        for count in segment_watcher.poll():
            on_segment(count)

    def _feed_ffmpeg() -> None:
        try:
            stdin.write(first_chunk)
            for _transport, chunk in chunk_iter:
                if stop_event is not None and stop_event.is_set():
                    break
                stdin.write(chunk)
                _maybe_notify_progress()
        except BrokenPipeError:
            detail = _read_ffmpeg_stderr(process)
            writer_error.append(
                FFmpegNotFoundError(
                    detail or "FFmpeg closed stdin (stream format not supported)"
                )
            )
        except Exception as exc:
            writer_error.append(exc)
        finally:
            try:
                stdin.close()
            except OSError:
                pass

    feeder = threading.Thread(target=_feed_ffmpeg, daemon=True)
    feeder.start()

    while feeder.is_alive():
        if stop_event is not None and stop_event.is_set():
            break
        _maybe_notify_progress()
        feeder.join(timeout=progress_interval_seconds)

    feeder.join()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

    _maybe_notify_progress(force=True)

    if writer_error and not (stop_event and stop_event.is_set()):
        raise writer_error[0]
    if process.returncode not in (0, None) and not (stop_event and stop_event.is_set()):
        detail = _read_ffmpeg_stderr(process)
        raise FFmpegNotFoundError(
            detail or f"FFmpeg HLS remux failed with exit code {process.returncode}"
        )
