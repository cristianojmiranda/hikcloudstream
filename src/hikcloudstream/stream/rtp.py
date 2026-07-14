"""RTP depacketization helpers."""

from __future__ import annotations

from pyezvizapi.stream import rtp_payload

from hikcloudstream._config import ANNEX_B_START_CODE


def rtp_h264_to_annexb(rtp_packet: bytes) -> bytes:
    """Depayload a single RTP packet (legacy — prefer ``RtpH264Depacketizer``)."""
    return RtpH264Depacketizer().feed_one(rtp_packet)


class RtpH264Depacketizer:
    """Stateful H.264 RTP depacketizer (single NAL + FU-A reassembly)."""

    def __init__(self) -> None:
        self._frag: bytearray | None = None

    def feed(self, rtp_packet: bytes) -> list[bytes]:
        chunk = self.feed_one(rtp_packet)
        return [chunk] if chunk else []

    def feed_one(self, rtp_packet: bytes) -> bytes:
        completed = self.feed_complete(rtp_packet)
        return completed[0] if completed else b""

    def feed_complete(self, rtp_packet: bytes) -> list[bytes]:
        if len(rtp_packet) < 12:
            return []
        try:
            payload = rtp_payload(rtp_packet)
        except Exception:
            return []
        if not payload:
            return []

        nal_type = payload[0] & 0x1F
        if nal_type == 28:
            return self._feed_fu_a(payload)
        if 1 <= nal_type <= 23:
            self._frag = None
            return [ANNEX_B_START_CODE + payload]
        return []

    def _feed_fu_a(self, payload: bytes) -> list[bytes]:
        if len(payload) < 2:
            return []

        fu_header = payload[1]
        if fu_header & 0x80:
            nri = payload[0] & 0x60
            nal_header = bytes([nri | (fu_header & 0x1F)])
            self._frag = bytearray(ANNEX_B_START_CODE)
            self._frag.extend(nal_header)
            self._frag.extend(payload[2:])
        elif self._frag is not None:
            self._frag.extend(payload[2:])
        else:
            return []

        if fu_header & 0x40:
            complete = bytes(self._frag)
            self._frag = None
            return [complete]
        return []
