"""Unit tests for H.264 parameter-set injection."""

from __future__ import annotations

from hikcloudstream._config import ANNEX_B_START_CODE
from hikcloudstream.stream.sinks.h264_ps import (
    H264ParameterSetInjector,
    split_annex_b_nals,
)


def _nal(nal_type: int, payload: bytes = b"\x01") -> bytes:
    header = bytes([(nal_type & 0x1F) | 0x60])
    return ANNEX_B_START_CODE + header + payload


def test_split_annex_b_nals_multiple_units() -> None:
    data = _nal(7, b"sps") + _nal(8, b"pps") + _nal(5, b"idr")
    assert len(split_annex_b_nals(data)) == 3


def test_injector_prepends_cached_ps_before_slice() -> None:
    injector = H264ParameterSetInjector()
    sps = _nal(7, b"sps")
    pps = _nal(8, b"pps")
    idr = _nal(5, b"idr")

    assert injector.feed(sps) == sps
    assert injector.feed(pps) == pps

    out = injector.feed(idr)
    assert out is not None
    assert out.startswith(sps + pps + idr)


def test_injector_drops_slices_until_ps_available() -> None:
    injector = H264ParameterSetInjector()
    assert injector.feed(_nal(5, b"idr")) is None

    assert injector.feed(_nal(7, b"sps")) is not None
    assert injector.feed(_nal(1, b"slice")) is None
    assert injector.feed(_nal(8, b"pps")) is not None

    out = injector.feed(_nal(5, b"idr"))
    assert out is not None
    assert out.startswith(_nal(7, b"sps") + _nal(8, b"pps"))


def test_injector_skips_duplicate_preface_when_chunk_has_ps() -> None:
    injector = H264ParameterSetInjector()
    injector.feed(_nal(7, b"sps"))
    injector.feed(_nal(8, b"pps"))

    combined = _nal(7, b"sps2") + _nal(8, b"pps2") + _nal(5, b"idr")
    out = injector.feed(combined)
    assert out == combined
