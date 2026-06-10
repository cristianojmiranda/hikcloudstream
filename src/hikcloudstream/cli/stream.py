#!/usr/bin/env python3
"""Live stream CLI — open Hik-Connect camera streams and capture HD frames."""

from __future__ import annotations

import argparse
import re
import sys
import threading
import time
from pathlib import Path

import httpx

from hikcloudstream import HikConnectClient
from hikcloudstream.cli._common import (
    add_auth_args,
    credentials_from_args,
    dump_camera_list_json,
    ensure_jpeg,
    image_dimensions,
    open_path,
    print_camera_list,
    resolve_camera,
    show_image,
)
from hikcloudstream.exceptions import HikCloudStreamError
from hikcloudstream.models import ClientConfig, StreamType
from hikcloudstream.stream import capture_live_snapshot, record_stream, require_ffmpeg
from hikcloudstream.stream.sinks.http import play_url, serve_stream_proxy


def _parse_duration(value: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(s|sec|secs|second|seconds|m|min|mins)?", value)
    if not match:
        raise argparse.ArgumentTypeError(
            f"invalid duration {value!r}; use examples like 10s or 1m"
        )
    amount = float(match.group(1))
    unit = match.group(2) or "s"
    if unit.startswith("m"):
        return amount * 60.0
    return amount


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open live Hik-Connect camera streams and capture HD snapshots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  hikcloudstream-stream user pass --list\n"
            "  hikcloudstream-stream user pass 1 --proxy\n"
            "  hikcloudstream-stream user pass 1 --proxy --show\n"
            "  hikcloudstream-stream user pass 1 -o frame-hd.jpg\n"
            "  hikcloudstream-stream user pass 1 --record clip.ts --duration 15s\n"
        ),
    )
    add_auth_args(parser)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Save a live-stream snapshot to this JPEG file",
    )
    parser.add_argument(
        "--record",
        type=Path,
        metavar="FILE",
        help="Record live stream to an MPEG-TS file",
    )
    parser.add_argument(
        "--duration",
        type=_parse_duration,
        default=10.0,
        help="Recording/snapshot warmup duration (default: 10s)",
    )
    parser.add_argument(
        "--proxy",
        action="store_true",
        help="Serve the live stream over HTTP (blocks until Ctrl+C)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Proxy bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8558,
        help="Proxy bind port (default: 8558)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="With --proxy, open the stream in ffplay",
    )
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="FFmpeg executable (default: ffmpeg)",
    )
    parser.add_argument(
        "--validate-code",
        help="Device encryption code (only if the app asks for one)",
    )
    parser.add_argument(
        "--main-stream",
        action="store_true",
        help="Use main stream (stream=1; higher resolution, not all cameras support it)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.list and args.camera is None:
        print("Specify a camera number or use --list.", file=sys.stderr)
        return 2

    action_count = sum(1 for flag in (args.output, args.record, args.proxy) if flag)
    if not args.list and action_count != 1:
        print(
            "Choose exactly one action: -o/--output, --record, or --proxy.",
            file=sys.stderr,
        )
        return 2

    try:
        creds = credentials_from_args(args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    config = ClientConfig(api_base_url=args.api)
    stream_type = StreamType.MAIN if args.main_stream else StreamType.AUTO

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

            camera = resolve_camera(cameras, args.camera)
            ffmpeg = require_ffmpeg(args.ffmpeg)

            if args.output:
                saved = capture_live_snapshot(
                    client,
                    camera,
                    args.output,
                    warmup_seconds=args.duration,
                    ffmpeg_path=ffmpeg,
                    validate_code=args.validate_code,
                    stream_type=stream_type,
                )
                image_bytes = saved.read_bytes()
                ensure_jpeg(image_bytes)
                width, height = image_dimensions(image_bytes)
                print(
                    f"Saved: {saved} ({camera.name} / ch {camera.channel_no}, "
                    f"{width}x{height}, live stream)"
                )
                if args.show:
                    try:
                        show_image(image_bytes)
                    except Exception:
                        open_path(saved)
                return 0

            if args.record:
                saved = record_stream(
                    client,
                    camera,
                    args.record,
                    duration_seconds=args.duration,
                    ffmpeg_path=ffmpeg,
                    validate_code=args.validate_code,
                    stream_type=stream_type,
                )
                print(
                    f"Recorded: {saved} ({camera.name} / ch {camera.channel_no}, "
                    f"{args.duration:.0f}s)"
                )
                return 0

            stream_url = (
                f"http://{args.host}:{args.port}/"
                f"{camera.device_serial}-{camera.channel_no}.ts"
            )
            if args.show:

                def _delayed_play() -> None:
                    time.sleep(0.8)
                    play_url(stream_url, player="ffplay")

                threading.Thread(target=_delayed_play, daemon=True).start()

            serve_stream_proxy(
                client,
                camera,
                host=args.host,
                port=args.port,
                ffmpeg_path=ffmpeg,
                validate_code=args.validate_code,
                stream_type=stream_type,
            )
            return 0
        except httpx.HTTPError as exc:
            print(f"HTTP error: {exc}", file=sys.stderr)
            return 1
        except HikCloudStreamError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
