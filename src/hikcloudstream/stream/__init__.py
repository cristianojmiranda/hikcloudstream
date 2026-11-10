"""Live streaming via Hik-Connect cloud VTM relay."""

from hikcloudstream.stream.presets import capture_preset_snapshot, record_preset_stream
from hikcloudstream.stream.probe import hls_stream_candidates, resolve_stream_type
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
from hikcloudstream.stream.zone import Zone, capture_zone_snapshot, record_zone_stream

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
    "hls_stream_candidates",
    "serve_stream_proxy",
    "Zone",
    "capture_zone_snapshot",
    "record_zone_stream",
    "capture_preset_snapshot",
    "record_preset_stream",
]
