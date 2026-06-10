#!/usr/bin/env python3
"""List Hik-Connect cameras for the configured account.

Requires: uv sync (core package only)
Env: HIK_CONNECT_USER, HIK_CONNECT_PASSWORD
"""

from __future__ import annotations

import os

from hikcloudstream import Credentials, HikConnectClient


def main() -> None:
    user = os.environ["HIK_CONNECT_USER"]
    password = os.environ["HIK_CONNECT_PASSWORD"]
    with HikConnectClient() as client:
        client.login(Credentials(user, password))
        for cam in client.list_cameras():
            print(cam.index, cam.name, cam.device_serial, cam.channel_no)


if __name__ == "__main__":
    main()
