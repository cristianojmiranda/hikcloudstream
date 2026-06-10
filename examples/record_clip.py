#!/usr/bin/env python3
"""Record a short MPEG-TS clip from the live cloud stream.

Requires: uv sync (core) + FFmpeg on PATH
Env: HIK_CONNECT_USER, HIK_CONNECT_PASSWORD
"""

from __future__ import annotations

import os
from pathlib import Path

from hikcloudstream import Credentials, HikConnectClient
from hikcloudstream.stream import record_stream


def main() -> None:
    user = os.environ["HIK_CONNECT_USER"]
    password = os.environ["HIK_CONNECT_PASSWORD"]
    with HikConnectClient() as client:
        client.login(Credentials(user, password))
        cameras = client.list_cameras()
        if not cameras:
            raise SystemExit("No cameras found")
        out = Path("clip.ts")
        record_stream(client, cameras[0], out, duration_seconds=15.0)
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
