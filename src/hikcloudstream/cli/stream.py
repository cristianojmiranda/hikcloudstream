#!/usr/bin/env python3
"""Live stream CLI — open Hik-Connect camera streams and capture HD frames."""

from __future__ import annotations

import argparse
import re
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from hikcloudstream import HikConnectClient
from hikcloudstream.cli._common import (
    add_auth_args,
    credentials_from_args,
    dump_camera_list_json,
    ensure_jpeg,
    image_dimensions,
    normalize_camera_args,
    open_path,
    print_camera_list,
    resolve_camera,
    show_image,
    verification_code_from_args,
)
from hikcloudstream.exceptions import HikCloudStreamError
from hikcloudstream.models import ClientConfig, StreamType
from hikcloudstream.stream import (
    Zone,
    capture_live_snapshot,
    capture_preset_snapshot,
    capture_zone_snapshot,
    record_preset_stream,
    record_stream,
    record_zone_stream,
    require_ffmpeg,
)
from hikcloudstream.stream.sinks.http import play_url, serve_stream_proxy


def _parse_duration(value: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(s|sec|secs|second|seconds|m|min|mins)?", value)
    if not match:
        raise argparse.ArgumentTypeError(
            f"invalid duration {value!r}; use examples like 10s or 1m"
        )
    amount = float(match.group(1))
    if amount <= 0:
        raise argparse.ArgumentTypeError("duration must be greater than zero")
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
            "  export HIK_CONNECT_USER=user@example.com HIK_CONNECT_PASSWORD=...\n"
            "  hikcloudstream-stream --list\n"
            "  hikcloudstream-stream 1 --proxy\n"
            "  hikcloudstream-stream 1 --record clip.ts --duration 15s\n"
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
        default=15.0,
        help="Recording/snapshot warmup duration (default: 15s)",
    )
    parser.add_argument(
        "--zone",
        type=Zone.parse,
        metavar="X,Y,W,H",
        help="Crop a live photo or recording to a normalized image zone (0..1)",
    )
    parser.add_argument(
        "--zone-preset",
        type=int,
        metavar="INDEX",
        help="Aim at an existing PTZ preset for a photo or recording",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List existing PTZ presets for the selected camera",
    )
    parser.add_argument(
        "--home-preset",
        type=int,
        metavar="INDEX",
        help="Return to this existing PTZ preset after --zone-preset",
    )
    parser.add_argument(
        "--ptz-settle",
        type=float,
        default=5.0,
        metavar="SECONDS",
        help="Wait for preset movement before capture (default: 5s)",
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
    parser.add_argument(
        "--player",
        choices=("hls", "mjpeg"),
        default="hls",
        help="Browser player: hls (default, sharper) or mjpeg (legacy)",
    )
    parser.add_argument(
        "--preview-fps",
        type=float,
        default=8.0,
        help="MJPEG preview frame rate when --player mjpeg (default: 8)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=75,
        metavar="Q",
        help="MJPEG JPEG quality 1–95 when --player mjpeg (default: 75)",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=0,
        metavar="PX",
        help="Max MJPEG width (0=auto: native substream, 1920 main)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    normalize_camera_args(args)

    if not args.list and args.camera is None:
        print("Specify a camera number or use --list.", file=sys.stderr)
        return 2

    action_count = sum(1 for flag in (args.output, args.record, args.proxy) if flag)
    if not (args.list or args.list_presets) and action_count != 1:
        print(
            "Choose exactly one action: -o/--output, --record, or --proxy.",
            file=sys.stderr,
        )
        return 2
    if args.zone and not (args.output or args.record):
        print("--zone requires --output or --record.", file=sys.stderr)
        return 2
    if (args.zone_preset is None) != (args.home_preset is None):
        print("--zone-preset and --home-preset must be provided together.", file=sys.stderr)
        return 2
    if args.zone_preset is not None and not (args.output or args.record):
        print("PTZ presets require --output or --record.", file=sys.stderr)
        return 2
    if args.list_presets and (action_count or args.zone or args.zone_preset is not None):
        print("--list-presets cannot be combined with capture or PTZ options.", file=sys.stderr)
        return 2
    if args.zone_preset is not None and (
        args.zone_preset < 1
        or args.home_preset < 1
        or args.zone_preset == args.home_preset
    ):
        print("PTZ zone and home presets must be distinct positive indices.", file=sys.stderr)
        return 2
    if args.ptz_settle < 0:
        print("--ptz-settle must not be negative.", file=sys.stderr)
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
            if args.list_presets:
                for index, name in client.list_presets(camera):
                    print(f"{index:>3}  {name}")
                return 0
            ffmpeg = require_ffmpeg(args.ffmpeg)

            if args.output:
                capture: Callable[..., Path]
                if args.zone_preset is not None:
                    capture = capture_preset_snapshot
                    capture_kwargs = {
                        "zone": args.zone,
                        "zone_preset": args.zone_preset,
                        "home_preset": args.home_preset,
                        "settle_seconds": args.ptz_settle,
                    }
                else:
                    capture = capture_zone_snapshot if args.zone else capture_live_snapshot
                    capture_kwargs = {"zone": args.zone} if args.zone else {}
                saved = capture(
                    client,
                    camera,
                    args.output,
                    **capture_kwargs,
                    warmup_seconds=args.duration,
                    ffmpeg_path=ffmpeg,
                    validate_code=verification_code_from_args(args),
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
                record: Callable[..., Path]
                if args.zone_preset is not None:
                    record = record_preset_stream
                    record_kwargs = {
                        "zone": args.zone,
                        "zone_preset": args.zone_preset,
                        "home_preset": args.home_preset,
                        "settle_seconds": args.ptz_settle,
                    }
                else:
                    record = record_zone_stream if args.zone else record_stream
                    record_kwargs = {"zone": args.zone} if args.zone else {}
                saved = record(
                    client,
                    camera,
                    args.record,
                    **record_kwargs,
                    duration_seconds=args.duration,
                    ffmpeg_path=ffmpeg,
                    validate_code=verification_code_from_args(args),
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
                validate_code=verification_code_from_args(args),
                stream_type=stream_type,
                player=args.player,
                preview_fps=args.preview_fps,
                jpeg_quality=args.jpeg_quality,
                max_width=args.max_width or None,
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
