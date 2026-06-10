"""Cloud snapshot decryption helpers."""

from __future__ import annotations

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from hikcloudstream._config import HIK_ENCODED_PREFIX, JPEG_MAGIC
from hikcloudstream.exceptions import CaptureError


def aes_key_material(value: str | None) -> bytes:
    raw = (value or "").encode("utf-8")
    if len(raw) >= 16:
        return raw[:16]
    return raw + b"\x00" * (16 - len(raw))


def decrypt_capture(raw: bytes, validate_code: str | None) -> bytes:
    """Decrypt Hik-Connect encrypted cloud snapshots."""
    if raw.startswith(JPEG_MAGIC):
        return raw
    if not raw.startswith(HIK_ENCODED_PREFIX):
        raise CaptureError(
            "unknown image format; provide validate_code for encrypted devices"
        )
    if len(raw) <= 48:
        raise CaptureError("encrypted payload too small")

    key = aes_key_material(validate_code)
    iv = aes_key_material("01234567")
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(raw[48:])
    try:
        return unpad(decrypted, AES.block_size)
    except ValueError:
        return decrypted
