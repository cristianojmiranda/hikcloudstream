"""HTTP HLS/MJPEG viewer and MPEG-TS proxy."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from hikcloudstream._config import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_PREVIEW_FPS,
    HLS_READY_TIMEOUT_MAIN,
    HLS_READY_TIMEOUT_SUB,
    MJPEG_BOUNDARY,
)
from hikcloudstream.client import HikConnectClient
from hikcloudstream.exceptions import (
    FFmpegNotFoundError,
    HikCloudStreamError,
    StreamNegotiationError,
)
from hikcloudstream.models import Camera, StreamType
from hikcloudstream.stream.probe import hls_stream_candidates, resolve_stream_type
from hikcloudstream.stream.session import (
    _resolve_stream_decrypt_key,
    open_live_stream,
    require_ffmpeg,
)
from hikcloudstream.stream.sinks.hls import (
    hls_content_type,
    prepare_hls_output_dir,
    stream_annex_b_to_hls,
    wait_for_hls_ready,
)
from hikcloudstream.stream.sinks.mjpeg import stream_mjpeg
from hikcloudstream.stream.sinks.mpegts import remux_stream_to_mpegts


def viewer_html(
    *,
    title: str,
    camera_name: str,
    vlc_url: str,
    player: str = "hls",
    stream_type: int = 2,
) -> bytes:
    if player == "hls":
        media = """
    <video id="live" controls autoplay muted playsinline></video>
    <p id="res" style="color:#888;font-size:0.85rem;margin:0.4rem 0"></p>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.7"></script>
    <script>
      const video = document.getElementById('live');
      const res = document.getElementById('res');
      const src = '/hls/index.m3u8';
      function showRes() {
        if (video.videoWidth) res.textContent = video.videoWidth + '×' + video.videoHeight + ' px';
      }
      if (window.Hls && Hls.isSupported()) {
        const hls = new Hls({ enableWorker: true, lowLatencyMode: true });
        hls.loadSource(src);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => { video.play().catch(() => {}); showRes(); });
        video.addEventListener('resize', showRes);
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = src;
        video.addEventListener('loadedmetadata', showRes);
        video.play().catch(() => {});
      } else {
        res.textContent = 'HLS not supported — open /mjpeg';
      }
    </script>"""
        player_note = "HLS player (H.264 passthrough, sharper than MJPEG)."
    else:
        media = '<img src="/mjpeg" alt="live stream" />'
        player_note = "MJPEG player. For sharper video use <code>--player hls</code>."

    hd_hint = ""
    if stream_type == 2:
        hd_hint = (
            " Cloud substream (~352–640px). HD: "
            "<code>--main-stream --player hls</code> (DVR channels 1–4 may fall back to SD)."
        )

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
    video, img {{
      max-width: 100%;
      width: auto;
      height: auto;
      max-height: 80vh;
      display: block;
      margin: 0 auto;
      background: #000;
      border-radius: 8px;
    }}
    p {{ color: #aaa; font-size: 0.9rem; line-height: 1.5; }}
    code {{ color: #ccc; }}
  </style>
</head>
<body>
  <main>
    <h1>{camera_name}</h1>
    {media}
    <p>
      {player_note} VLC/ffplay: <code>{vlc_url}</code>.
      Stream auto (2=SD substream, 1=HD main).{hd_hint}
    </p>
  </main>
</body>
</html>
"""
    return page.encode("utf-8")


def _forced_stream_type(stream_type: StreamType | int | None) -> int | None:
    if stream_type is None or stream_type == StreamType.AUTO:
        return None
    return int(stream_type)


def _start_hls_ingest(
    client: HikConnectClient,
    camera: Camera,
    *,
    candidate: int,
    hls_dir: Path,
    ffmpeg_path: str,
    stop: threading.Event,
    errors: list[str],
) -> threading.Thread:
    def _run() -> None:
        try:
            with open_live_stream(client, camera, stream_type=candidate) as session:
                stream_info = session.start()
                if stream_info.result not in (0, None):
                    raise StreamNegotiationError(
                        f"VTM stream negotiation failed (code {stream_info.result})"
                    )
                stream_annex_b_to_hls(
                    session._client,
                    hls_dir,
                    ffmpeg_path=ffmpeg_path,
                    stop_event=stop,
                )
        except Exception as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def _bootstrap_hls_ingest(
    client: HikConnectClient,
    camera: Camera,
    *,
    selected_stream: int,
    forced_stream_type: int | None,
    ffmpeg_path: str,
) -> tuple[Path, threading.Event, threading.Thread, int, str]:
    hls_dir = Path(tempfile.mkdtemp(prefix="hikcloudstream-hls-"))
    hls_stop = threading.Event()
    hls_errors: list[str] = []
    ingest_thread: threading.Thread | None = None
    fallback_note = ""
    candidates = hls_stream_candidates(
        client,
        camera,
        selected_stream,
        forced_stream_type,
    )

    started = False
    for index, candidate in enumerate(candidates):
        hls_errors.clear()
        if index > 0:
            hls_stop.set()
            if ingest_thread is not None:
                ingest_thread.join(timeout=2.0)
            hls_stop = threading.Event()
            prepare_hls_output_dir(hls_dir)

        ingest_thread = _start_hls_ingest(
            client,
            camera,
            candidate=candidate,
            hls_dir=hls_dir,
            ffmpeg_path=ffmpeg_path,
            stop=hls_stop,
            errors=hls_errors,
        )
        ready_timeout = HLS_READY_TIMEOUT_MAIN if candidate == 1 else HLS_READY_TIMEOUT_SUB
        if wait_for_hls_ready(
            hls_dir,
            timeout=ready_timeout,
            ingest_thread=ingest_thread,
            errors=hls_errors,
        ):
            selected_stream = candidate
            started = True
            if candidate == 2 and forced_stream_type == 1:
                fallback_note = (
                    "Main stream (HD) not decodable on this camera; "
                    "using substream (SD ~352–640px)."
                )
            break
        hls_stop.set()
        ingest_thread.join(timeout=2.0)

    if not started or ingest_thread is None:
        hls_stop.set()
        detail = hls_errors[-1] if hls_errors else "timeout waiting for HLS segments"
        if "6106" in detail:
            detail += (
                " (VTM session busy — wait ~30s after Ctrl+C before reconnecting; "
                "main-only cameras do not need --main-stream)"
            )
        shutil.rmtree(hls_dir, ignore_errors=True)
        raise HikCloudStreamError(f"HLS ingest failed: {detail}")

    return hls_dir, hls_stop, ingest_thread, selected_stream, fallback_note


class MjpegServer:
    """Embedded HTTP server with HLS/MJPEG and MPEG-TS routes."""

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
        player: str = "hls",
        preview_fps: float = DEFAULT_PREVIEW_FPS,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        max_width: int | None = None,
    ) -> None:
        self._client = client
        self._camera = camera
        self._host = host
        self._port = port
        self._ffmpeg_path = ffmpeg_path
        self._validate_code = validate_code
        self._stream_type_arg = stream_type
        self._player = player
        self._preview_fps = preview_fps
        self._jpeg_quality = jpeg_quality
        self._max_width = max_width
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
            player=self._player,
            preview_fps=self._preview_fps,
            jpeg_quality=self._jpeg_quality,
            max_width=self._max_width,
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
    player: str = "hls",
    preview_fps: float = DEFAULT_PREVIEW_FPS,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    max_width: int | None = None,
) -> str:
    ffmpeg = require_ffmpeg(ffmpeg_path)
    decrypt_key = _resolve_stream_decrypt_key(client, camera, validate_code)
    forced = _forced_stream_type(stream_type)
    if forced is None:
        selected_stream = resolve_stream_type(client, camera)
    else:
        selected_stream = forced

    stream_path = path or f"/{camera.device_serial}-{camera.channel_no}.ts"
    if not stream_path.startswith("/"):
        stream_path = f"/{stream_path}"

    viewer_mode = player.lower()
    if viewer_mode not in ("hls", "mjpeg"):
        raise HikCloudStreamError(f"unsupported player {player!r}; use hls or mjpeg")

    hls_dir: Path | None = None
    hls_stop: threading.Event | None = None
    hls_root: Path | None = None
    fallback_note = ""

    if viewer_mode == "hls":
        hls_dir, hls_stop, _ingest_thread, selected_stream, fallback_note = _bootstrap_hls_ingest(
            client,
            camera,
            selected_stream=selected_stream,
            forced_stream_type=forced,
            ffmpeg_path=ffmpeg,
        )
        hls_root = hls_dir.resolve()

    preview_max_width = max_width
    if preview_max_width is None and viewer_mode == "mjpeg":
        preview_max_width = 1920 if selected_stream == 1 else None

    class Handler(BaseHTTPRequestHandler):
        def _browser_wants_html(self) -> bool:
            accept = self.headers.get("Accept", "")
            return "text/html" in accept

        def _serve_hls_file(self, request_path: str) -> None:
            assert hls_root is not None
            rel = request_path.removeprefix("/hls/")
            if not rel or ".." in rel.split("/"):
                self.send_error(403, "Forbidden")
                return
            file_path = (hls_root / rel).resolve()
            if not str(file_path).startswith(str(hls_root)):
                self.send_error(403, "Forbidden")
                return
            if not file_path.is_file():
                self.send_error(404, "Not Found")
                return
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", hls_content_type(file_path))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            request_path = self.path.split("?", 1)[0]
            if request_path in ("/", "/watch"):
                body = viewer_html(
                    title=f"Hik-Connect — {camera.name}",
                    camera_name=f"{camera.name} (ch {camera.channel_no})",
                    vlc_url=stream_path,
                    player=viewer_mode,
                    stream_type=selected_stream,
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if hls_root is not None and request_path.startswith("/hls/"):
                try:
                    self._serve_hls_file(request_path)
                except (BrokenPipeError, ConnectionResetError):
                    return
                return

            if request_path == "/mjpeg":
                try:
                    with open_live_stream(
                        client,
                        camera,
                        stream_type=selected_stream,
                    ) as session:
                        session.start()
                        self.send_response(200)
                        self.send_header(
                            "Content-Type",
                            f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY.decode()}",
                        )
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        stream_mjpeg(
                            session._client,
                            self.wfile,
                            frame_fps=preview_fps,
                            validate_code=decrypt_key,
                            stream_type=selected_stream,
                            jpeg_quality=jpeg_quality,
                            max_width=preview_max_width,
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
                    ) as session:
                        session.start()
                        self.send_response(200)
                        self.send_header("Content-Type", "video/mp2t")
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        remux_stream_to_mpegts(
                            session._client,
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
    if viewer_mode == "hls":
        print(f"HLS:          http://{host}:{port}/hls/index.m3u8")
    print(f"MJPEG:        http://{host}:{port}/mjpeg")
    print(f"MPEG-TS:      {stream_url}  (VLC/ffplay)")
    print(f"Stream type:  {selected_stream} (auto: 2=SD substream, 1=HD main)")
    print(f"Player:       {viewer_mode}")
    if fallback_note:
        print(f"Note:         {fallback_note}")
    if viewer_mode == "mjpeg":
        print(f"Preview:      {preview_fps:.0f} fps, JPEG q={jpeg_quality}")
    print("Open the viewer in your browser. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    finally:
        if hls_stop is not None:
            hls_stop.set()
        server.server_close()
        if hls_dir is not None and hls_dir.exists():
            shutil.rmtree(hls_dir, ignore_errors=True)
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
