"""Shared CLI helpers."""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
from pathlib import Path

from hikcloudstream._config import JPEG_MAGIC
from hikcloudstream.exceptions import CameraNotFoundError
from hikcloudstream.models import Camera, ClientConfig, Credentials

DEFAULT_API = ClientConfig().api_base_url


def credentials_from_args(args: argparse.Namespace) -> Credentials:
    username = args.username or os.environ.get("HIK_CONNECT_USER", "")
    password = args.password or os.environ.get("HIK_CONNECT_PASSWORD", "")
    if not username or not password:
        raise RuntimeError(
            "username and password required (arguments or HIK_CONNECT_USER / HIK_CONNECT_PASSWORD)"
        )
    return Credentials(username=username, password=password)


def add_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "username",
        nargs="?",
        default=None,
        help="Hik-Connect account (or HIK_CONNECT_USER env)",
    )
    parser.add_argument(
        "password",
        nargs="?",
        default=None,
        help="Hik-Connect password (or HIK_CONNECT_PASSWORD env)",
    )
    parser.add_argument(
        "camera",
        nargs="?",
        type=int,
        help="Camera number from --list (1-based index)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available cameras and exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print camera list as JSON (with --list)",
    )
    parser.add_argument(
        "--api",
        default=DEFAULT_API,
        help=f"API base URL (default: {DEFAULT_API})",
    )


def resolve_camera(cameras: list[Camera], camera_no: int) -> Camera:
    if camera_no < 1 or camera_no > len(cameras):
        raise CameraNotFoundError(
            f"invalid camera {camera_no}. Use --list (1..{len(cameras)})."
        )
    return cameras[camera_no - 1]


def print_camera_list(cameras: list[Camera]) -> None:
    if not cameras:
        print("No cameras found for this account.")
        return
    print(f"{'#':>3}  {'Camera':<28} {'Device':<20} {'Serial':<12} Ch")
    print("-" * 80)
    for camera in cameras:
        print(
            f"{camera.index:>3}  {camera.name[:28]:<28} "
            f"{camera.device_name[:20]:<20} {camera.device_serial:<12} "
            f"{camera.channel_no}"
        )


def dump_camera_list_json(cameras: list[Camera]) -> None:
    print(
        json.dumps(
            [
                {
                    "index": c.index,
                    "name": c.name,
                    "device": c.device_name,
                    "deviceSerial": c.device_serial,
                    "channelNo": c.channel_no,
                }
                for c in cameras
            ],
            indent=2,
            ensure_ascii=False,
        )
    )


def image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes))
    return image.size


def save_image(image_bytes: bytes, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)
    return path


def show_image(image_bytes: bytes) -> None:
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image.show()


def open_path(path: Path) -> None:
    if sys.platform.startswith("linux"):
        subprocess.run(["xdg-open", str(path)], check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        raise RuntimeError("no default viewer configured for this platform")


def ensure_jpeg(image_bytes: bytes) -> None:
    if not image_bytes.startswith(JPEG_MAGIC):
        raise RuntimeError("output is not a valid JPEG")
