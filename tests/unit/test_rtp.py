"""Unit tests for RTP depacketization."""

from __future__ import annotations

from hikcloudstream._config import ANNEX_B_START_CODE
from hikcloudstream.stream.rtp import rtp_h264_to_annexb


def test_rtp_empty_returns_empty() -> None:
    assert rtp_h264_to_annexb(b"") == b""


def test_rtp_single_nal_type_7_sps() -> None:
    # RTP header (12 bytes) + single NAL SPS (type 7)
    rtp = bytes([0x80, 0x60, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    nal = bytes([0x67, 0x42, 0x00, 0x1F])  # SPS NAL type 7
    result = rtp_h264_to_annexb(rtp + nal)
    assert result.startswith(ANNEX_B_START_CODE)
    assert result[4] & 0x1F == 7


def test_rtp_fu_a_start_fragment() -> None:
    # FU-A type 28, start bit set, reconstructs NAL header
    rtp = bytes([0x80, 0x60, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    fu_a = bytes([0x7C, 0x85, 0x88, 0x42, 0x00, 0x1F])  # SPS fragment
    result = rtp_h264_to_annexb(rtp + fu_a)
    assert result.startswith(ANNEX_B_START_CODE)
    assert len(result) > len(ANNEX_B_START_CODE) + 1


def test_rtp_unknown_nal_returns_empty() -> None:
    rtp = bytes([0x80, 0x60, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    nal = bytes([0x9D, 0xFF, 0xFF])  # filler / unknown
    assert rtp_h264_to_annexb(rtp + nal) == b""
