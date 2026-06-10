#!/usr/bin/env python3
"""Save a cloud snapshot (352x288) for the first camera.

Requires: uv sync (core)
Env: HIK_CONNECT_USER, HIK_CONNECT_PASSWORD
"""

from __future__ import annotations

import os
from pathlib import Path

from hikcloudstream import Credentials, HikConnectClient


def main() -> None:
    user = os.environ["HIK_CONNECT_USER"]
    password = os.environ["HIK_CONNECT_PASSWORD"]
    with HikConnectClient() as client:
        client.login(Credentials(user, password))
        cameras = client.list_cameras()
        if not cameras:
            raise SystemExit("No cameras found")
        jpeg = client.capture_snapshot(cameras[0])
        out = Path("snapshot.jpg")
        out.write_bytes(jpeg)
        print(f"Wrote {out} ({len(jpeg)} bytes)")


if __name__ == "__main__":
    main()
