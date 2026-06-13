"""Unit tests for HLS fMP4 sink helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from hikcloudstream.stream.sinks.hls import (
    open_hls_remux_process,
    prepare_hls_output_dir,
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
        assert "-c" in process.args
        copy_idx = process.args.index("-c")
        assert process.args[copy_idx + 1] == "copy"
        assert "fmp4" in process.args
        assert str(output / "index.m3u8") in process.args
    finally:
        if process.stdin:
            process.stdin.close()
        process.kill()
        process.wait()
