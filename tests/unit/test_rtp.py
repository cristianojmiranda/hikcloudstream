"""Unit tests for RTP depacketization."""

from __future__ import annotations

from hikcloudstream._config import ANNEX_B_START_CODE
from hikcloudstream.stream.rtp import RtpH264Depacketizer, rtp_h264_to_annexb


def _rtp(payload: bytes) -> bytes:
    header = bytes([0x80, 0x60, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    return header + payload


def test_rtp_empty_returns_empty() -> None:
    assert rtp_h264_to_annexb(b"") == b""


def test_rtp_single_nal_type_7_sps() -> None:
    # RTP header (12 bytes) + single NAL SPS (type 7)
    nal = bytes([0x67, 0x42, 0x00, 0x1F])  # SPS NAL type 7
    result = rtp_h264_to_annexb(_rtp(nal))
    assert result.startswith(ANNEX_B_START_CODE)
    assert result[4] & 0x1F == 7


def test_rtp_fu_a_reassembles_fragments() -> None:
    depacketizer = RtpH264Depacketizer()
    start = bytes([0x7C, 0x85, 0xAA, 0xBB])
    middle = bytes([0x7C, 0x05, 0xCC])
    end = bytes([0x7C, 0x45, 0xDD, 0xEE])

    assert depacketizer.feed_complete(_rtp(start)) == []
    assert depacketizer.feed_complete(_rtp(middle)) == []
    complete = depacketizer.feed_complete(_rtp(end))
    assert len(complete) == 1
    assert complete[0].startswith(ANNEX_B_START_CODE)
    assert complete[0][4] & 0x1F == 5
    assert complete[0].endswith(bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE]))


def test_rtp_fu_a_start_fragment_waits_for_end() -> None:
    fu_a = bytes([0x7C, 0x85, 0x88, 0x42, 0x00, 0x1F])  # SPS fragment (start only)
    assert rtp_h264_to_annexb(_rtp(fu_a)) == b""


def test_rtp_unknown_nal_returns_empty() -> None:
    nal = bytes([0x9D, 0xFF, 0xFF])  # filler / unknown
    assert rtp_h264_to_annexb(_rtp(nal)) == b""
