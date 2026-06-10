#!/usr/bin/env python3
"""Cloud snapshot CLI — low-resolution thumbnail via Hik-Connect API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from hikcloudstream import CLOUD_CAPTURE_MAX, HikConnectClient
from hikcloudstream.cli._common import (
    add_auth_args,
    credentials_from_args,
    dump_camera_list_json,
    ensure_jpeg,
    image_dimensions,
    open_path,
    print_camera_list,
    resolve_camera,
    save_image,
    show_image,
)
from hikcloudstream.exceptions import HikCloudStreamError
from hikcloudstream.models import ClientConfig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture a cloud snapshot from Hik-Connect cameras.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  hikcloudstream-snapshot user pass --list\n"
            "  hikcloudstream-snapshot user pass 3\n"
            "  hikcloudstream-snapshot user pass 3 -o camera3.jpg\n"
            "  hikcloudstream-stream user pass 3 -o frame-hd.jpg   # higher-res live frame\n"
        ),
    )
    add_auth_args(parser)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Save snapshot to this file (default: camera-<n>.jpg)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open the snapshot with the default image viewer",
    )
    parser.add_argument(
        "--validate-code",
        help="Device encryption code (only needed for encrypted snapshots)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = ClientConfig(api_base_url=args.api)

    try:
        creds = credentials_from_args(args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    with HikConnectClient(config) as client:
        try:
            client.login(creds)
            cameras = client.list_cameras()

            if args.list:
                if args.json:
                    dump_camera_list_json(cameras)
                else:
                    print_camera_list(cameras)
                return 0

            if args.camera is None:
                print("Specify a camera number or use --list.", file=sys.stderr)
                return 2

            camera = resolve_camera(cameras, args.camera)
            image_bytes = client.capture_snapshot(
                camera,
                validate_code=args.validate_code,
            )
            ensure_jpeg(image_bytes)

            output_path = args.output or Path(f"camera-{args.camera}.jpg")
            saved = save_image(image_bytes, output_path)

            width, height = image_dimensions(image_bytes)
            print(
                f"Saved: {saved} ({camera.name} / ch {camera.channel_no}, "
                f"{width}x{height})"
            )
            if (width, height) == CLOUD_CAPTURE_MAX:
                print(
                    "Note: cloud snapshot is capped at "
                    f"{CLOUD_CAPTURE_MAX[0]}x{CLOUD_CAPTURE_MAX[1]} by Hik-Connect API. "
                    "Use hikcloudstream-stream for a live-stream frame.",
                    file=sys.stderr,
                )

            if args.show:
                try:
                    show_image(image_bytes)
                except Exception:
                    open_path(saved)

            return 0
        except httpx.HTTPError as exc:
            print(f"HTTP error: {exc}", file=sys.stderr)
            return 1
        except HikCloudStreamError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
