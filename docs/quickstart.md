# Quickstart

## Install

```bash
uv sync --extra viewer
# or: pip install "hikcloudstream[viewer]"
```

Install [FFmpeg](https://ffmpeg.org/) for recording and HD frame capture.

## Environment (optional)

```bash
cp .env.example .env
# fill HIK_CONNECT_USER and HIK_CONNECT_PASSWORD
```

## List cameras

```python
from hikcloudstream import Credentials, HikConnectClient

with HikConnectClient() as client:
    client.login(Credentials("user@example.com", "your_password"))
    for cam in client.list_cameras():
        print(cam.index, cam.name, cam.device_serial, cam.channel_no)
```

## Cloud snapshot

```python
from pathlib import Path
from hikcloudstream import Credentials, HikConnectClient

with HikConnectClient() as client:
    client.login(Credentials("user@example.com", "your_password"))
    cameras = client.list_cameras()
    jpeg = client.capture_snapshot(cameras[0])
    Path("thumb.jpg").write_bytes(jpeg)
```

Resolution is capped at **352×288** by the Hik-Connect cloud API.

## Live stream frame (HD)

```python
from pathlib import Path
from hikcloudstream import Credentials, HikConnectClient
from hikcloudstream.stream import capture_live_snapshot

with HikConnectClient() as client:
    client.login(Credentials("user@example.com", "your_password"))
    cameras = client.list_cameras()
    capture_live_snapshot(client, cameras[0], Path("frame.jpg"), warmup_seconds=6.0)
```

## MJPEG browser viewer

```python
from hikcloudstream import Credentials, HikConnectClient
from hikcloudstream.stream import MjpegServer

with HikConnectClient() as client:
    client.login(Credentials("user@example.com", "your_password"))
    cameras = client.list_cameras()
    MjpegServer(client, cameras[0], host="127.0.0.1", port=8558).serve_forever()
```

Open `http://127.0.0.1:8558/`.
