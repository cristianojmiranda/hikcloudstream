"""VTM session lifecycle and high-level stream helpers."""

from __future__ import annotations

import io
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pyezvizapi.cloud_stream import get_vtm_info, get_vtm_page_list, parse_vtm_server_public_key
from pyezvizapi.stream import VtmStreamClient, build_vtm_url

from hikcloudstream.client import HikConnectClient
from hikcloudstream.exceptions import FFmpegNotFoundError, StreamNegotiationError, TokenError
from hikcloudstream.models import Camera, StreamType
from hikcloudstream.stream.adapter import HikConnectStreamAdapter
from hikcloudstream.stream.crypto import decrypt_h264_for_ffmpeg
from hikcloudstream.stream.probe import with_stream_type
from hikcloudstream.stream.sinks.annex_b import iter_annex_b_chunks, write_stream_payloads
from hikcloudstream.stream.sinks.mpegts import remux_annex_b_to_mpegts, remux_stream_incremental
from hikcloudstream.stream.tokens import get_vtdu_tokens


def _find_vtm_resource(
    resources: list[Any],
    serial: str,
    *,
    channel: int | None,
) -> dict[str, Any] | None:
    serial_resources = [
        item
        for item in resources
        if isinstance(item, dict) and item.get("deviceSerial") == serial
    ]
    if channel is None:
        return serial_resources[0] if serial_resources else None

    channel_text = str(channel)
    return next(
        (
            item
            for item in serial_resources
            if str(item.get("localIndex")) == channel_text
        ),
        None,
    )


def build_cloud_stream_info(
    adapter: HikConnectStreamAdapter,
    camera: Camera,
    *,
    client_type: int = 55,
    token_index: int = 0,
    refresh_vtm: bool = True,
    stream_type: int = 1,
) -> dict[str, Any]:
    pagelist = get_vtm_page_list(adapter)
    resources = pagelist.get("resourceInfos") or []
    vtms = pagelist.get("VTM") or {}
    if not isinstance(resources, list) or not isinstance(vtms, dict):
        raise StreamNegotiationError("VTM pagelist response is missing resource metadata")

    resource = _find_vtm_resource(
        resources,
        camera.device_serial,
        channel=camera.channel_no,
    )
    if not isinstance(resource, dict):
        raise StreamNegotiationError(
            f"could not find VTM resource for {camera.device_serial} "
            f"channel {camera.channel_no}"
        )

    resource_id = resource.get("resourceId")
    vtm = vtms.get(resource_id)
    if not isinstance(vtm, dict):
        raise StreamNegotiationError(f"could not find VTM server for resource {resource_id}")

    tokens = get_vtdu_tokens(adapter)
    try:
        vtdu_token = tokens[token_index]
    except IndexError as exc:
        raise TokenError(f"VTDU token index out of range: {token_index}") from exc

    stream_channel = camera.channel_no
    if refresh_vtm:
        vtm = {
            **vtm,
            **get_vtm_info(adapter, camera.device_serial, stream_channel),
        }

    host = vtm.get("externalIp") or vtm.get("domain") or vtm.get("internalIp")
    if not isinstance(host, str) or not host.strip():
        raise StreamNegotiationError(f"could not find VTM endpoint for resource {resource_id}")
    port_value = vtm.get("port")
    if not isinstance(port_value, (int, str)) or not str(port_value).isdigit():
        raise StreamNegotiationError(f"could not find VTM port for resource {resource_id}")
    port = int(port_value)

    stream_url = with_stream_type(
        build_vtm_url(
            host.strip(),
            port,
            camera.device_serial,
            str(resource.get("streamBizUrl") or ""),
            vtdu_token,
            channel=stream_channel,
            client_type=client_type,
        ),
        stream_type,
    )
    return {
        "resource": resource,
        "vtm": vtm,
        "vtm_public_key": parse_vtm_server_public_key(vtm),
        "vtdu_token": vtdu_token,
        "stream_url": stream_url,
        "stream_type": stream_type,
    }


class LiveStreamSession:
    """Context manager wrapping a VTM TCP live stream."""

    def __init__(
        self,
        client: VtmStreamClient,
        *,
        stream_type: int,
        device_serial: str,
        channel_no: int,
    ) -> None:
        self._client = client
        self._stream_type = stream_type
        self._device_serial = device_serial
        self._channel_no = channel_no
        self._started = False

    def __enter__(self) -> LiveStreamSession:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @property
    def stream_type(self) -> int:
        return self._stream_type

    @property
    def device_serial(self) -> str:
        return self._device_serial

    @property
    def channel_no(self) -> int:
        return self._channel_no

    def start(self):
        self._started = True
        return self._client.start()

    def iter_rtp_packets(self) -> Iterator[bytes]:
        from pyezvizapi.stream import VtmChannel

        for packet in self._client.iter_packets():
            if packet.channel in (VtmChannel.STREAM, VtmChannel.ENCRYPTED_STREAM) and packet.body:
                yield packet.body

    def iter_annex_b_chunks(
        self,
        *,
        max_packets: int | None = None,
        duration_seconds: float | None = None,
        allow_encrypted: bool = False,
    ) -> Iterator[bytes]:
        for _transport, chunk in iter_annex_b_chunks(
            self._client,
            max_packets=max_packets,
            duration_seconds=duration_seconds,
            allow_encrypted=allow_encrypted,
        ):
            yield chunk

    def __repr__(self) -> str:
        return (
            f"LiveStreamSession(device={self._device_serial!r}, "
            f"channel={self._channel_no}, stream={self._stream_type})"
        )


def _stream_type_value(stream_type: StreamType | int | None) -> int | None:
    if stream_type is None or stream_type == StreamType.AUTO:
        return None
    return int(stream_type)


def open_live_stream(
    client: HikConnectClient,
    camera: Camera,
    *,
    client_type: int = 55,
    token_index: int = 0,
    refresh_vtm: bool = True,
    stream_type: StreamType | int | None = StreamType.AUTO,
    timeout: float = 15.0,
) -> LiveStreamSession:
    adapter = HikConnectStreamAdapter(client)
    explicit = _stream_type_value(stream_type)
    if explicit is None:
        from hikcloudstream.stream.probe import resolve_stream_type

        selected_stream = resolve_stream_type(client, camera, client_type=client_type)
    else:
        selected_stream = explicit

    info = build_cloud_stream_info(
        adapter,
        camera,
        client_type=client_type,
        token_index=token_index,
        refresh_vtm=refresh_vtm,
        stream_type=selected_stream,
    )
    vtm_client = VtmStreamClient(info["stream_url"], timeout=timeout)
    return LiveStreamSession(
        vtm_client,
        stream_type=selected_stream,
        device_serial=camera.device_serial,
        channel_no=camera.channel_no,
    )


def require_ffmpeg(ffmpeg_path: str = "ffmpeg") -> str:
    resolved = shutil.which(ffmpeg_path)
    if not resolved:
        raise FFmpegNotFoundError(
            f"FFmpeg not found ({ffmpeg_path!r}). Install ffmpeg for live stream capture."
        )
    return resolved


def _resolve_stream_decrypt_key(
    client: HikConnectClient,
    camera: Camera,
    validate_code: str | None,
) -> str | None:
    if not validate_code:
        return None
    try:
        return client.query_device_encrypt_key(camera.device_serial, validate_code)
    except Exception:
        return validate_code


def record_to_file(
    session: LiveStreamSession,
    output_path: Path,
    *,
    duration_seconds: float = 10.0,
    ffmpeg_path: str = "ffmpeg",
    decrypt_key: str | None = None,
) -> Path:
    ffmpeg = require_ffmpeg(ffmpeg_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stream_info = session.start()
    if stream_info.result not in (0, None):
        raise StreamNegotiationError(
            f"VTM stream negotiation failed (code {stream_info.result}). "
            "VTDU auth may be unavailable from this network."
        )
    with output_path.open("wb") as handle:
        if decrypt_key:
            buffer = io.BytesIO()
            transport = write_stream_payloads(
                session._client,
                buffer,
                max_packets=None,
                duration_seconds=duration_seconds,
            )
            payload = decrypt_h264_for_ffmpeg(buffer.getvalue(), decrypt_key)
            remux_annex_b_to_mpegts(payload, handle, ffmpeg_path=ffmpeg, transport=transport)
        else:
            remux_stream_incremental(
                session._client,
                handle,
                ffmpeg_path=ffmpeg,
                duration_seconds=duration_seconds,
            )
    return output_path


def capture_frame(
    session: LiveStreamSession,
    output_path: Path,
    *,
    warmup_seconds: float = 4.0,
    ffmpeg_path: str = "ffmpeg",
    decrypt_key: str | None = None,
) -> Path:
    temp_video = output_path.with_suffix(".ts")
    try:
        record_to_file(
            session,
            temp_video,
            duration_seconds=warmup_seconds,
            ffmpeg_path=ffmpeg_path,
            decrypt_key=decrypt_key,
        )
        return _extract_frame(temp_video, output_path, ffmpeg_path=ffmpeg_path)
    finally:
        temp_video.unlink(missing_ok=True)


def _extract_frame(
    video_path: Path,
    output_path: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
    seek_seconds: float | None = None,
) -> Path:
    ffmpeg = require_ffmpeg(ffmpeg_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if seek_seconds is not None:
        command.extend(["-ss", str(seek_seconds)])
    command.extend(
        [
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-update",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
    )
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FFmpegNotFoundError(
            f"FFmpeg frame extract failed: {result.stderr.strip() or result.stdout}"
        )
    return output_path


def record_stream(
    client: HikConnectClient,
    camera: Camera,
    output_path: Path,
    *,
    duration_seconds: float = 10.0,
    ffmpeg_path: str = "ffmpeg",
    validate_code: str | None = None,
    stream_type: StreamType | int | None = StreamType.AUTO,
) -> Path:
    decrypt_key = _resolve_stream_decrypt_key(client, camera, validate_code)
    with open_live_stream(client, camera, stream_type=stream_type) as session:
        return record_to_file(
            session,
            output_path,
            duration_seconds=duration_seconds,
            ffmpeg_path=ffmpeg_path,
            decrypt_key=decrypt_key,
        )


def capture_live_snapshot(
    client: HikConnectClient,
    camera: Camera,
    output_path: Path,
    *,
    warmup_seconds: float = 4.0,
    ffmpeg_path: str = "ffmpeg",
    validate_code: str | None = None,
    stream_type: StreamType | int | None = StreamType.AUTO,
) -> Path:
    decrypt_key = _resolve_stream_decrypt_key(client, camera, validate_code)
    with open_live_stream(client, camera, stream_type=stream_type) as session:
        return capture_frame(
            session,
            output_path,
            warmup_seconds=warmup_seconds,
            ffmpeg_path=ffmpeg_path,
            decrypt_key=decrypt_key,
        )
