#!/usr/bin/env python3
"""Start a local HLS or MJPEG HTTP viewer for the first camera.

Requires: uv sync --extra viewer + FFmpeg on PATH
Env: HIK_CONNECT_USER, HIK_CONNECT_PASSWORD

Open http://127.0.0.1:8558/ in a browser. Press Ctrl+C to stop.
"""

from __future__ import annotations

import os

from hikcloudstream import Credentials, HikConnectClient
from hikcloudstream.stream import MjpegServer


def main() -> None:
    user = os.environ["HIK_CONNECT_USER"]
    password = os.environ["HIK_CONNECT_PASSWORD"]
    with HikConnectClient() as client:
        client.login(Credentials(user, password))
        cameras = client.list_cameras()
        if not cameras:
            raise SystemExit("No cameras found")
        MjpegServer(client, cameras[0], player="hls").serve_forever()


if __name__ == "__main__":
    main()
