# Streaming

## Overview

Live video uses the **Hik-Connect cloud VTM relay**:

```
Login → VTDU tokens → TCP to regional VTM → RTP/H.264 → depacketize → sinks
```

## Session API

```python
from hikcloudstream import Credentials, HikConnectClient
from hikcloudstream.models import StreamType
from hikcloudstream.stream import LiveStreamSession, open_live_stream

with HikConnectClient() as client:
    client.login(Credentials("user@example.com", "your_password"))
    cameras = client.list_cameras()

    with open_live_stream(client, cameras[0], stream_type=StreamType.AUTO) as session:
        session.start()
        for chunk in session.iter_annex_b_chunks():
            ...  # feed GStreamer, aiortc, file, etc.
```

`LiveStreamSession` is a context manager — the VTM socket is always closed on exit.

## High-level helpers

| Function | Output |
|----------|--------|
| `record_stream(client, camera, path)` | MPEG-TS file |
| `capture_live_snapshot(client, camera, path)` | JPEG from live stream |
| `serve_stream_proxy(client, camera)` | HTTP MJPEG + MPEG-TS |
| `MjpegServer(client, camera).serve_forever()` | Same as proxy |

## Sinks (library integration)

Lower-level sinks under `hikcloudstream.stream.sinks` for custom ingest/fan-out:

| Module | Function | Output |
|--------|----------|--------|
| `annex_b` | `iter_annex_b_chunks(session)` | Raw H.264 Annex B chunks |
| `mpegts` | `stream_annex_b_to_mpegts(...)` | MPEG-TS on stdout or file |
| `mjpeg` | `stream_mjpeg(...)` | Multipart MJPEG (PyAV decode + JPEG encode) |
| `hls` | `stream_annex_b_to_hls(...)` | Rolling HLS fMP4 segments on disk |

### HLS fMP4 (passthrough)

For many browser viewers from a **single** VTM ingest, remux H.264 without re-encoding:

```python
import threading
from pathlib import Path

from hikcloudstream.stream.sinks.hls import stream_annex_b_to_hls

stop = threading.Event()

def on_segment(count: int) -> None:
    print("segments ready:", count)

stream_annex_b_to_hls(
    vtm_client,
    Path("/tmp/hls/ch1"),
    segment_seconds=2.0,
    list_size=6,
    stop_event=stop,
    on_segment=on_segment,
)
# Serve Path("/tmp/hls/ch1/index.m3u8") + seg_*.m4s + init.mp4 via HTTP
```

Requires **FFmpeg** on PATH. Uses `-c copy` (no transcode). Segment files roll under `delete_segments+append_list+independent_segments+omit_endlist`.

### MJPEG tuning

`stream_mjpeg` accepts optional `jpeg_quality` (50–95, default 82), `max_width` (default 1920 main / 1408 sub), and `require_keyframe` (wait for an IDR before emitting frames). At quality ≥ 90, JPEG uses 4:4:4 chroma subsampling for sharper color.

## Stream type selection

`StreamType.AUTO` (default) probes substream (`stream=2`) for 5 seconds; if no valid RTP, uses main (`stream=1`).

Some DVR channels use proprietary RTP on the main stream — substream is often required for decodable H.264.

## Scaling

**Each consumer opens its own VTM TCP session** to the cloud. For many viewers:

1. Single ingest (one `open_live_stream`)
2. Fan-out via HLS, WebRTC (MediaMTX), or shared MJPEG buffer

See [limitations.md](limitations.md).

## Encrypted streams

If the device uses video encryption, pass `validate_code` to `record_stream` / `capture_live_snapshot`. The MJPEG HTTP viewer does not support encrypted live decode yet.
