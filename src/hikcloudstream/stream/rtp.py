"""RTP depacketization helpers."""

from __future__ import annotations

from pyezvizapi.stream import rtp_payload

from hikcloudstream._config import ANNEX_B_START_CODE


def rtp_h264_to_annexb(rtp_packet: bytes) -> bytes:
    """Depayload H.264 RTP (FU-A / single NAL) into Annex B for FFmpeg."""
    if len(rtp_packet) < 12:
        return b""
    try:
        payload = rtp_payload(rtp_packet)
    except Exception:
        return b""
    if not payload:
        return b""

    nal_type = payload[0] & 0x1F
    if nal_type == 28:
        fu_header = payload[1]
        if fu_header & 0x80:
            nri = payload[0] & 0x60
            nal_header = bytes([nri | (fu_header & 0x1F)])
            return ANNEX_B_START_CODE + nal_header + payload[2:]
        return payload[2:]
    if 1 <= nal_type <= 23:
        return ANNEX_B_START_CODE + payload
    return b""
