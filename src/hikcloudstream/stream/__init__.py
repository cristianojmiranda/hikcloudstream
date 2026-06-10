"""Live streaming via Hik-Connect cloud VTM relay."""

from hikcloudstream.stream.probe import resolve_stream_type
from hikcloudstream.stream.session import (
    LiveStreamSession,
    capture_frame,
    capture_live_snapshot,
    open_live_stream,
    record_stream,
    record_to_file,
    require_ffmpeg,
)
from hikcloudstream.stream.sinks.http import MjpegServer, serve_stream_proxy

__all__ = [
    "LiveStreamSession",
    "MjpegServer",
    "capture_frame",
    "capture_live_snapshot",
    "open_live_stream",
    "record_stream",
    "record_to_file",
    "require_ffmpeg",
    "resolve_stream_type",
    "serve_stream_proxy",
]
