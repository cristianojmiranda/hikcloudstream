"""Unit tests for stream crypto helpers."""

from __future__ import annotations

from hikcloudstream.capture import aes_key_material
from hikcloudstream.stream.crypto import looks_encrypted_h264


def test_aes_key_material_pads_short() -> None:
    assert len(aes_key_material("abc")) == 16
    assert aes_key_material("abc") == b"abc" + b"\x00" * 13


def test_aes_key_material_truncates_long() -> None:
    assert len(aes_key_material("a" * 32)) == 16


def test_looks_encrypted_empty() -> None:
    assert looks_encrypted_h264(b"") is False


def test_looks_encrypted_plain_annex_b() -> None:
    # Minimal Annex B with SPS + slice-like NAL headers (unencrypted pattern)
    data = (
        b"\x00\x00\x00\x01\x67\x42\x00\x1f"
        b"\x00\x00\x00\x01\x68\xce\x3c\x80"
        b"\x00\x00\x00\x01\x65\x88\x80\x10"
    )
    assert looks_encrypted_h264(data) is False


def test_looks_encrypted_ciphertext_heuristic() -> None:
    # Random bytes with start codes but no valid SPS+PPS+slice pattern
    data = b"\x00\x00\x00\x01" + bytes(range(256)) * 4
    assert looks_encrypted_h264(data) is True
