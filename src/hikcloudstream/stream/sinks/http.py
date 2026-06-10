"""HTTP MJPEG viewer and MPEG-TS proxy."""

from __future__ import annotations

import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from hikcloudstream._config import MJPEG_BOUNDARY
from hikcloudstream.client import HikConnectClient
from hikcloudstream.exceptions import FFmpegNotFoundError
from hikcloudstream.models import Camera, StreamType
from hikcloudstream.stream.probe import resolve_stream_type
from hikcloudstream.stream.session import (
    _resolve_stream_decrypt_key,
    open_live_stream,
    require_ffmpeg,
)
from hikcloudstream.stream.sinks.mjpeg import stream_mjpeg
from hikcloudstream.stream.sinks.mpegts import remux_stream_to_mpegts


def viewer_html(*, title: str, camera_name: str, vlc_url: str) -> bytes:
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      background: #111;
      color: #eee;
      font-family: system-ui, sans-serif;
      display: grid;
      place-items: center;
      min-height: 100vh;
    }}
    main {{ width: min(96vw, 1280px); padding: 1rem; }}
    h1 {{ font-size: 1.1rem; font-weight: 600; margin: 0 0 0.75rem; }}
    img {{
      width: 100%;
      background: #000;
      border-radius: 8px;
      aspect-ratio: 16 / 9;
      object-fit: contain;
    }}
    p {{ color: #aaa; font-size: 0.9rem; line-height: 1.5; }}
    code {{ color: #ccc; }}
  </style>
</head>
<body>
  <main>
    <h1>{camera_name}</h1>
    <img src="/mjpeg" alt="live stream" />
    <p>
      MJPEG browser player. For VLC/ffplay use
      <code>{vlc_url}</code> (Chrome downloads .ts files instead of playing them).
      Stream type is auto-selected (substream or main). Force main stream via
      <code>StreamType.MAIN</code> in the API or <code>--main-stream</code> in the CLI.
    </p>
  </main>
</body>
</html>
"""
    return page.encode("utf-8")


class MjpegServer:
    """Embedded HTTP server with MJPEG and MPEG-TS routes."""

    def __init__(
        self,
        client: HikConnectClient,
        camera: Camera,
        *,
        host: str = "127.0.0.1",
        port: int = 8558,
        path: str | None = None,
        ffmpeg_path: str = "ffmpeg",
        validate_code: str | None = None,
        stream_type: StreamType | int | None = StreamType.AUTO,
    ) -> None:
        self._client = client
        self._camera = camera
        self._host = host
        self._port = port
        self._ffmpeg_path = ffmpeg_path
        self._validate_code = validate_code
        self._stream_type_arg = stream_type
        self._path = path or f"/{camera.device_serial}-{camera.channel_no}.ts"
        if not self._path.startswith("/"):
            self._path = f"/{self._path}"
        self._server: ThreadingHTTPServer | None = None

    @property
    def viewer_url(self) -> str:
        return f"http://{self._host}:{self._port}/"

    def serve_forever(self) -> str:
        return serve_stream_proxy(
            self._client,
            self._camera,
            host=self._host,
            port=self._port,
            path=self._path,
            ffmpeg_path=self._ffmpeg_path,
            validate_code=self._validate_code,
            stream_type=self._stream_type_arg,
        )

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.shutdown()


def serve_stream_proxy(
    client: HikConnectClient,
    camera: Camera,
    *,
    host: str = "127.0.0.1",
    port: int = 8558,
    path: str | None = None,
    ffmpeg_path: str = "ffmpeg",
    validate_code: str | None = None,
    stream_type: StreamType | int | None = StreamType.AUTO,
) -> str:
    ffmpeg = require_ffmpeg(ffmpeg_path)
    decrypt_key = _resolve_stream_decrypt_key(client, camera, validate_code)
    if stream_type is None or stream_type == StreamType.AUTO:
        selected_stream = resolve_stream_type(client, camera)
    else:
        selected_stream = int(stream_type)

    stream_path = path or f"/{camera.device_serial}-{camera.channel_no}.ts"
    if not stream_path.startswith("/"):
        stream_path = f"/{stream_path}"

    class Handler(BaseHTTPRequestHandler):
        def _browser_wants_html(self) -> bool:
            accept = self.headers.get("Accept", "")
            return "text/html" in accept

        def do_GET(self) -> None:
            request_path = self.path.split("?", 1)[0]
            if request_path in ("/", "/watch"):
                body = viewer_html(
                    title=f"Hik-Connect — {camera.name}",
                    camera_name=f"{camera.name} (ch {camera.channel_no})",
                    vlc_url=stream_path,
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if request_path == "/mjpeg":
                try:
                    with open_live_stream(
                        client,
                        camera,
                        stream_type=selected_stream,
                    ) as vtm_stream:
                        vtm_stream.start()
                        self.send_response(200)
                        self.send_header(
                            "Content-Type",
                            f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY.decode()}",
                        )
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        stream_mjpeg(
                            vtm_stream._client,
                            self.wfile,
                            validate_code=decrypt_key,
                            stream_type=selected_stream,
                        )
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as exc:
                    if not self.wfile.closed:
                        self.send_error(502, str(exc))
                return

            if request_path == stream_path:
                if self._browser_wants_html():
                    self.send_response(302)
                    self.send_header("Location", "/")
                    self.end_headers()
                    return
                try:
                    with open_live_stream(
                        client,
                        camera,
                        stream_type=selected_stream,
                    ) as vtm_stream:
                        vtm_stream.start()
                        self.send_response(200)
                        self.send_header("Content-Type", "video/mp2t")
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        remux_stream_to_mpegts(
                            vtm_stream._client,
                            self.wfile,
                            ffmpeg_path=ffmpeg,
                            duration_seconds=None,
                            live=True,
                        )
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as exc:
                    if not self.wfile.closed:
                        self.send_error(502, str(exc))
                return

            self.send_error(404, "Not Found")

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    viewer_url = f"http://{host}:{port}/"
    stream_url = f"http://{host}:{port}{stream_path}"
    print(f"Live viewer:  {viewer_url}")
    print(f"MJPEG:        http://{host}:{port}/mjpeg")
    print(f"MPEG-TS:      {stream_url}  (VLC/ffplay)")
    print(f"Stream type:  {selected_stream} (auto: 2=substream, 1=main)")
    print("Open the viewer in your browser. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return viewer_url


def play_url(url: str, *, player: str = "ffplay") -> None:
    resolved = shutil.which(player)
    if not resolved:
        raise FFmpegNotFoundError(
            f"{player!r} not found. Install ffmpeg (ffplay) or open the URL manually."
        )
    subprocess.run(
        [resolved, "-loglevel", "quiet", "-window_title", "hikcloudstream", url],
        check=False,
    )
