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
