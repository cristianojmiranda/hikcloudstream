"""Raw H.264 Annex B chunk iteration from VTM packets."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

from pyezvizapi.stream import StreamTransport, VtmChannel, detect_transport

from hikcloudstream.exceptions import EncryptedStreamError
from hikcloudstream.stream.rtp import rtp_h264_to_annexb

if TYPE_CHECKING:
    from pyezvizapi.stream import VtmStreamClient


def packet_to_annex_b(packet_body: bytes, transport: StreamTransport) -> bytes:
    if transport == StreamTransport.RTP:
        return rtp_h264_to_annexb(packet_body)
    return packet_body


def iter_annex_b_chunks(
    stream: VtmStreamClient,
    *,
    max_packets: int | None = None,
    duration_seconds: float | None = None,
    allow_encrypted: bool = False,
) -> Iterator[tuple[StreamTransport, bytes]]:
    deadline = None if duration_seconds is None else time.monotonic() + duration_seconds
    transport = StreamTransport.UNKNOWN

    for packet in stream.iter_packets(max_packets=max_packets):
        if deadline is not None and time.monotonic() >= deadline:
            break
        if packet.channel not in (VtmChannel.STREAM, VtmChannel.ENCRYPTED_STREAM):
            continue
        if packet.encrypted and not allow_encrypted:
            raise EncryptedStreamError(
                "received encrypted VTM stream packet; provide validate_code or "
                "use a camera without video encryption"
            )
        if not packet.body:
            continue
        packet_transport = detect_transport(packet.body)
        if transport == StreamTransport.UNKNOWN and packet_transport != StreamTransport.UNKNOWN:
            transport = packet_transport
        active_transport = (
            packet_transport if packet_transport != StreamTransport.UNKNOWN else transport
        )
        chunk = packet_to_annex_b(packet.body, active_transport)
        if chunk:
            yield active_transport, chunk


def write_stream_payloads(
    stream: VtmStreamClient,
    output,
    *,
    max_packets: int | None,
    duration_seconds: float | None = None,
    allow_encrypted: bool = False,
) -> StreamTransport:
    transport = StreamTransport.UNKNOWN
    for active_transport, chunk in iter_annex_b_chunks(
        stream,
        max_packets=max_packets,
        duration_seconds=duration_seconds,
        allow_encrypted=allow_encrypted,
    ):
        if transport == StreamTransport.UNKNOWN:
            transport = active_transport
        output.write(chunk)
    output.flush()
    return transport
