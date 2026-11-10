"""Security boundaries for cloud addresses, CLI arguments, and viewer HTML."""

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from hikcloudstream.cli._common import (
    credentials_from_args,
    normalize_camera_args,
    verification_code_from_args,
)
from hikcloudstream.client import HikConnectClient, _trusted_cloud_origin
from hikcloudstream.exceptions import AuthenticationError
from hikcloudstream.models import Credentials
from hikcloudstream.stream import session as stream_session
from hikcloudstream.stream.sinks.http import viewer_html


@pytest.mark.parametrize(
    "address",
    [
        "http://api.hik-connect.com",
        "https://api.hik-connect.com.evil.example",
        "https://api.hik-connect.com@evil.example",
        "https://api.hik-connect.com/path",
        "https://api.hik-connect.com:8443",
    ],
)
def test_untrusted_cloud_address_rejected(address: str) -> None:
    with pytest.raises(AuthenticationError):
        _trusted_cloud_origin(address)


def test_regional_cloud_address_accepted() -> None:
    assert _trusted_cloud_origin("apiie.ezvizlife.com") == "https://apiie.ezvizlife.com"


def test_login_rejects_untrusted_redirect() -> None:
    with HikConnectClient() as client:
        client._login_once = lambda _credentials: "evil.example"  # type: ignore[method-assign]
        with pytest.raises(AuthenticationError):
            client.login(Credentials("user@example.com", "password"))


def test_camera_number_with_environment_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIK_CONNECT_USER", "user@example.com")
    args = Namespace(username="2", password=None, camera=None)
    normalize_camera_args(args)
    assert (args.username, args.camera) == (None, 2)


def test_cli_reads_dotenv_without_overriding_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(
        "HIK_CONNECT_USER=file-user\n"
        "HIK_CONNECT_PASSWORD=file-password\n"
        "HIK_CONNECT_VALIDATE_CODE=file-code\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HIK_CONNECT_USER", "exported-user")
    monkeypatch.delenv("HIK_CONNECT_PASSWORD", raising=False)
    monkeypatch.delenv("HIK_CONNECT_VALIDATE_CODE", raising=False)
    args = Namespace(username="1", password=None, camera=None, validate_code=None)
    normalize_camera_args(args)
    assert args.camera == 1
    assert credentials_from_args(args) == Credentials("exported-user", "file-password")
    assert verification_code_from_args(args) == "file-code"


def test_viewer_escapes_camera_name() -> None:
    page = viewer_html(
        title="<script>alert(1)</script>",
        camera_name="<img src=x onerror=alert(1)>",
        vlc_url="/stream?x=<bad>",
    ).decode()
    assert "<script>alert(1)</script>" not in page
    assert "<img src=x onerror=alert(1)>" not in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page
    assert "/stream?x=&lt;bad&gt;" in page


def test_recording_failure_preserves_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "clip.ts"
    output.write_bytes(b"existing recording")
    monkeypatch.setattr(stream_session, "require_ffmpeg", lambda _path: "ffmpeg")

    def fail_remux(*_args: object, **_kwargs: object) -> None:
        raise stream_session.StreamNegotiationError("stream failed")

    monkeypatch.setattr(stream_session, "remux_stream_incremental", fail_remux)
    fake_session = SimpleNamespace(start=lambda: SimpleNamespace(result=0), _client=object())
    with pytest.raises(stream_session.StreamNegotiationError):
        stream_session.record_to_file(fake_session, output)
    assert output.read_bytes() == b"existing recording"


def test_undecodable_recording_preserves_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "clip.ts"
    output.write_bytes(b"existing recording")
    monkeypatch.setattr(stream_session, "require_ffmpeg", lambda _path: "ffmpeg")

    def write_bad_video(_stream: object, handle: object, **_kwargs: object) -> None:
        handle.write(b"remuxed but undecodable")

    def reject_video(
        _path: Path, *, ffmpeg_path: str, verification_code_supplied: bool
    ) -> None:
        assert ffmpeg_path == "ffmpeg"
        assert verification_code_supplied is False
        raise stream_session.EncryptedStreamError("no frame")

    monkeypatch.setattr(stream_session, "remux_stream_incremental", write_bad_video)
    monkeypatch.setattr(stream_session, "_verify_recording", reject_video)
    fake_session = SimpleNamespace(start=lambda: SimpleNamespace(result=0), _client=object())
    with pytest.raises(stream_session.EncryptedStreamError):
        stream_session.record_to_file(fake_session, output)
    assert output.read_bytes() == b"existing recording"
