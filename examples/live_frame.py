#!/usr/bin/env python3
"""Capture one HD frame from the live cloud stream.

Requires: uv sync --extra viewer (PyAV optional; FFmpeg required on PATH)
Env: HIK_CONNECT_USER, HIK_CONNECT_PASSWORD
"""

from __future__ import annotations

import os
from pathlib import Path

from hikcloudstream import Credentials, HikConnectClient
from hikcloudstream.stream import capture_live_snapshot


def main() -> None:
    user = os.environ["HIK_CONNECT_USER"]
    password = os.environ["HIK_CONNECT_PASSWORD"]
    with HikConnectClient() as client:
        client.login(Credentials(user, password))
        cameras = client.list_cameras()
        if not cameras:
            raise SystemExit("No cameras found")
        out = Path("frame-hd.jpg")
        capture_live_snapshot(client, cameras[0], out, warmup_seconds=6.0)
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
