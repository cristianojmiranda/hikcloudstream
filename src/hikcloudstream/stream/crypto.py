"""Encrypted live-stream decryption helpers."""

from __future__ import annotations

from Crypto.Cipher import AES
from pyezvizapi.stream import (
    HIKVISION_NAL_ENCRYPTED_PREFIX_LENGTH,
    _find_h264_nal_start_codes,
    _find_hevc_nal_start_codes,
    _find_nal_start_codes,
    _h264_nal_type,
    _hevc_nal_type,
    detect_hikvision_ps_video_nalu_header_size,
)

from hikcloudstream.capture import aes_key_material


def looks_encrypted_h264(data: bytes) -> bool:
    """Best-effort detect ciphertext Annex B (FFmpeg cannot decode as-is)."""
    if not data:
        return False

    saw_sps_or_pps = False
    saw_idr_or_slice = False
    for pos, length in _find_nal_start_codes(data, 0, min(len(data), 120_000)):
        header_pos = pos + length
        if header_pos >= len(data):
            continue
        nal_header = data[header_pos]
        if (nal_header & 0x80) != 0:
            continue
        nal_type = nal_header & 0x1F
        if nal_type in {7, 8}:
            saw_sps_or_pps = True
        if nal_type in {1, 5}:
            saw_idr_or_slice = True

    return not (saw_sps_or_pps and saw_idr_or_slice)


def decrypt_hikvision_annex_b_video(
    data: bytes,
    key: str | bytes,
    *,
    nalu_header_size: int | None = None,
) -> bytes:
    """Decrypt encrypted H.264/HEVC Annex B from RTP-depacketized VTM streams."""
    if nalu_header_size is None:
        nalu_header_size = detect_hikvision_ps_video_nalu_header_size(
            data,
            key,
            default=0,
        )
    if nalu_header_size is None:
        nalu_header_size = 0
    if nalu_header_size < 0:
        raise ValueError("nalu_header_size must be non-negative")

    key_bytes = key.encode() if isinstance(key, str) else key
    aes_key = key_bytes.ljust(16, b"\0")[:16]
    output = bytearray(data)
    pending_block_positions: list[int] = []
    pending_block = bytearray()
    active_nal = False
    active_nal_decrypted = active_nal_body_start = 0
    find_nal_start_codes = (
        _find_nal_start_codes
        if nalu_header_size == 0
        else _find_h264_nal_start_codes
        if nalu_header_size == 1
        else _find_hevc_nal_start_codes
    )

    def reset_nal_state() -> None:
        nonlocal active_nal, active_nal_body_start, active_nal_decrypted
        pending_block_positions.clear()
        pending_block.clear()
        active_nal = False
        active_nal_decrypted = active_nal_body_start = 0

    def decrypt_nal_body_segment(start: int, end: int) -> None:
        nonlocal active_nal_decrypted
        if end <= start:
            return
        remaining = HIKVISION_NAL_ENCRYPTED_PREFIX_LENGTH - active_nal_decrypted
        if remaining <= 0:
            return
        decrypt_end = min(end, start + remaining)
        for pos in range(start, decrypt_end):
            pending_block_positions.append(pos)
            pending_block.append(output[pos])
            active_nal_decrypted += 1
            if len(pending_block) != AES.block_size:
                continue
            cipher = AES.new(aes_key, AES.MODE_CBC, iv=bytes(AES.block_size))
            decrypted = cipher.decrypt(bytes(pending_block))
            for block_pos, decrypted_byte in zip(
                pending_block_positions,
                decrypted,
                strict=True,
            ):
                output[block_pos] = decrypted_byte
            pending_block_positions.clear()
            pending_block.clear()

    def starts_plausible_encrypted_h264_nal(start: int, end: int) -> bool:
        if end - start < AES.block_size:
            return False
        cipher = AES.new(aes_key, AES.MODE_CBC, iv=bytes(AES.block_size))
        decrypted_header = cipher.decrypt(bytes(output[start : start + AES.block_size]))[0]
        nal_type = decrypted_header & 0x1F
        return 1 <= nal_type <= 23

    def is_post_prefix_tail_lookalike(start_code_pos: int, start_code_len: int) -> bool:
        if nalu_header_size == 0:
            return True
        if nalu_header_size == 1:
            nal_type = _h264_nal_type(data, start_code_pos, start_code_len)
            return nal_type is None or not 1 <= nal_type <= 5
        nal_type = _hevc_nal_type(data, start_code_pos, start_code_len)
        return nal_type is None or nal_type >= 32

    payload_start = 0
    payload_end = len(data)
    nal_starts = find_nal_start_codes(data, payload_start, payload_end)
    segment_start = payload_start
    if not nal_starts:
        return bytes(output)

    for idx, (start_code_pos, start_code_len) in enumerate(nal_starts):
        decrypt_end = nal_starts[idx + 1][0] if idx + 1 < len(nal_starts) else payload_end
        if active_nal:
            candidate_decrypted = active_nal_decrypted + max(
                0,
                start_code_pos - segment_start,
            )
            if candidate_decrypted < HIKVISION_NAL_ENCRYPTED_PREFIX_LENGTH:
                if nalu_header_size == 0 and (
                    candidate_decrypted == 0
                    or not starts_plausible_encrypted_h264_nal(
                        start_code_pos + start_code_len,
                        decrypt_end,
                    )
                ):
                    continue
                if nalu_header_size != 0 and candidate_decrypted == 0:
                    continue
        if (
            active_nal
            and active_nal_decrypted >= HIKVISION_NAL_ENCRYPTED_PREFIX_LENGTH
            and start_code_pos > active_nal_body_start + HIKVISION_NAL_ENCRYPTED_PREFIX_LENGTH
            and is_post_prefix_tail_lookalike(start_code_pos, start_code_len)
        ):
            continue
        if active_nal and segment_start < start_code_pos:
            decrypt_nal_body_segment(segment_start, start_code_pos)
        reset_nal_state()
        active_nal = True
        decrypt_start = start_code_pos + start_code_len + nalu_header_size
        active_nal_body_start = decrypt_start
        decrypt_nal_body_segment(decrypt_start, decrypt_end)
        segment_start = decrypt_end
    if active_nal and segment_start < payload_end:
        decrypt_nal_body_segment(segment_start, payload_end)

    return bytes(output)


def decrypt_h264_for_ffmpeg(h264_bytes: bytes, decrypt_key: str | None) -> bytes:
    """Return Annex B bytes suitable for FFmpeg, decrypting when needed."""
    if not decrypt_key:
        return h264_bytes
    return decrypt_hikvision_annex_b_video(
        h264_bytes,
        aes_key_material(decrypt_key),
        nalu_header_size=0,
    )
