"""Unit tests for stream URL helpers."""

from __future__ import annotations

from hikcloudstream.stream.probe import with_stream_type


def test_with_stream_type_appends() -> None:
    url = "ysproto://example.com:8554/live?dev=ABC&chn=1"
    assert "stream=2" in with_stream_type(url, 2)


def test_with_stream_type_replaces() -> None:
    url = "ysproto://example.com:8554/live?dev=ABC&stream=1"
    result = with_stream_type(url, 2)
    assert "stream=2" in result
    assert "stream=1" not in result


def test_with_stream_type_idempotent() -> None:
    url = "ysproto://example.com:8554/live?stream=2"
    assert with_stream_type(url, 2) == url
