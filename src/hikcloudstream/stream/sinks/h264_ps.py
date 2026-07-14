"""H.264 parameter-set handling for Annex B passthrough sinks."""

from __future__ import annotations

from hikcloudstream._config import ANNEX_B_START_CODE

_SLICE_NAL_TYPES = frozenset({1, 2, 3, 4, 5})


def _nal_type(nal: bytes) -> int:
    offset = 0
    if nal.startswith(ANNEX_B_START_CODE):
        offset = 4
    elif len(nal) >= 3 and nal[:3] == b"\x00\x00\x01":
        offset = 3
    if offset >= len(nal):
        return 0
    return nal[offset] & 0x1F


def split_annex_b_nals(data: bytes) -> list[bytes]:
    """Split an Annex B buffer into individual NAL units (start codes preserved)."""
    if not data:
        return []

    positions: list[int] = []
    index = 0
    while index < len(data):
        if data.startswith(ANNEX_B_START_CODE, index):
            positions.append(index)
            index += 4
            continue
        if index + 3 <= len(data) and data[index : index + 3] == b"\x00\x00\x01":
            positions.append(index)
            index += 3
            continue
        index += 1

    if not positions:
        return [data]

    nals: list[bytes] = []
    for idx, start in enumerate(positions):
        end = positions[idx + 1] if idx + 1 < len(positions) else len(data)
        nals.append(data[start:end])
    return nals


class H264ParameterSetInjector:
    """
    Cache SPS/PPS and prepend them before slice NALs.

    Hik main streams (e.g. DVR channel 17) often emit IDR/slice NALs before PPS,
    which breaks FFmpeg ``-c copy`` HLS remux with ``non-existing PPS 0 referenced``.
    """

    def __init__(self) -> None:
        self._sps: bytes | None = None
        self._pps: bytes | None = None

    def feed(self, chunk: bytes) -> bytes | None:
        nals = split_annex_b_nals(chunk)
        if not nals:
            return None

        for nal in nals:
            nal_type = _nal_type(nal)
            if nal_type == 7:
                self._sps = nal
            elif nal_type == 8:
                self._pps = nal

        chunk_has_ps = any(_nal_type(nal) in {7, 8} for nal in nals)
        out: list[bytes] = []
        prefaced = False

        for nal in nals:
            nal_type = _nal_type(nal)
            if nal_type in _SLICE_NAL_TYPES:
                if self._sps is None or self._pps is None:
                    continue
                if not prefaced and not chunk_has_ps:
                    out.extend((self._sps, self._pps))
                    prefaced = True
                out.append(nal)
            else:
                out.append(nal)

        if not out:
            return None
        return b"".join(out)
