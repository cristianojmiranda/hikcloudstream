"""Unit tests for HLS fMP4 sink helpers."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hikcloudstream.models import Camera, StreamType
from hikcloudstream.stream.probe import hls_stream_candidates
from hikcloudstream.stream.sinks.hls import (
    _SegmentWatcher,
    hls_output_ready,
    open_hls_remux_process,
    prepare_hls_output_dir,
    wait_for_hls_ready,
)


def test_prepare_hls_output_dir_cleans_existing(tmp_path: Path) -> None:
    output = tmp_path / "ch1"
    output.mkdir()
    (output / "old.m4s").write_bytes(b"old")
    prepare_hls_output_dir(output)
    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_open_hls_remux_process_args(tmp_path: Path) -> None:
    pytest.importorskip("shutil")
    ffmpeg = __import__("shutil").which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg not installed")

    output = tmp_path / "ch2"
    prepare_hls_output_dir(output)
    process = open_hls_remux_process(output, ffmpeg, segment_seconds=2.0, list_size=6)
    try:
        assert process.stdin is not None
        assert "+genpts+igndts+nobuffer" in process.args
        assert "-use_wallclock_as_timestamps" in process.args
        copy_idx = process.args.index("-c")
        assert process.args[copy_idx + 1] == "copy"
        assert "fmp4" in process.args
        assert str(output / "index.m3u8") in process.args
    finally:
        if process.stdin:
            process.stdin.close()
        process.kill()
        process.wait()


def test_segment_watcher_detects_sequential_segments(tmp_path: Path) -> None:
    output = tmp_path / "ch1"
    output.mkdir()
    watcher = _SegmentWatcher(output)
    assert watcher.poll() == []

    (output / "seg_00001.m4s").write_bytes(b"a")
    assert watcher.poll() == [1]

    assert watcher.poll() == []
    (output / "seg_00002.m4s").write_bytes(b"b")
    (output / "seg_00003.m4s").write_bytes(b"c")
    assert watcher.poll() == [2, 3]


def test_segment_watcher_skips_deleted_middle_segment(tmp_path: Path) -> None:
    """Rolling window may delete seg_00002 before poll — watcher must still see seg_00003."""
    output = tmp_path / "ch1"
    output.mkdir()
    watcher = _SegmentWatcher(output)

    (output / "seg_00001.m4s").write_bytes(b"a")
    watcher.poll()

    (output / "seg_00003.m4s").write_bytes(b"c")
    assert watcher.poll() == [2]


def test_hls_output_ready_requires_playlist(tmp_path: Path) -> None:
    output = tmp_path / "hls"
    output.mkdir()
    assert hls_output_ready(output) is False
    (output / "index.m3u8").write_text("#EXTM3U\n")
    assert hls_output_ready(output) is False
    (output / "init.mp4").write_bytes(b"ftyp")
    assert hls_output_ready(output) is True


def test_hls_output_ready_accepts_segment_without_init(tmp_path: Path) -> None:
    output = tmp_path / "hls"
    output.mkdir()
    (output / "index.m3u8").write_text("#EXTM3U\n")
    (output / "seg_00000.m4s").write_bytes(b"seg")
    assert hls_output_ready(output) is True


def test_wait_for_hls_ready_returns_false_when_thread_dies_with_error(tmp_path: Path) -> None:
    output = tmp_path / "hls"
    output.mkdir()
    errors = ["FFmpeg closed stdin"]

    def _dead_thread() -> None:
        return

    thread = threading.Thread(target=_dead_thread)
    thread.start()
    thread.join()

    assert wait_for_hls_ready(output, timeout=0.5, ingest_thread=thread, errors=errors) is False


def test_hls_stream_candidates_main_only_camera() -> None:
    camera = Camera(
        index=17,
        name="Placa",
        device_serial="G20104145",
        channel_no=17,
        device_name="NVR",
    )
    client = MagicMock()

    with patch(
        "hikcloudstream.stream.session.build_cloud_stream_info",
        return_value={"stream_url": "ysproto://x/live?stream=2"},
    ), patch(
        "hikcloudstream.stream.probe.substream_has_media",
        return_value=False,
    ):
        assert hls_stream_candidates(client, camera, 1, StreamType.MAIN) == [1]


def test_hls_stream_candidates_main_with_substream_fallback() -> None:
    camera = Camera(
        index=1,
        name="Camera 01",
        device_serial="G20104145",
        channel_no=1,
        device_name="NVR",
    )
    client = MagicMock()

    with patch(
        "hikcloudstream.stream.session.build_cloud_stream_info",
        return_value={"stream_url": "ysproto://x/live?stream=2"},
    ), patch(
        "hikcloudstream.stream.probe.substream_has_media",
        return_value=True,
    ):
        assert hls_stream_candidates(client, camera, 1, StreamType.MAIN) == [1, 2]


def test_hls_stream_candidates_auto_substream_no_fallback() -> None:
    camera = Camera(
        index=1,
        name="Camera 01",
        device_serial="G20104145",
        channel_no=1,
        device_name="NVR",
    )
    client = MagicMock()

    assert hls_stream_candidates(client, camera, 2, None) == [2]
