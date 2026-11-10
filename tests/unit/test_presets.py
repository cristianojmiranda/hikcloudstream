"""PTZ preset capture returns to home even after capture failure."""

from types import SimpleNamespace

import pytest

from hikcloudstream.stream import presets


def test_preset_zone_returns_home_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    moves: list[int] = []
    client = SimpleNamespace(goto_preset=lambda _camera, index: moves.append(index))
    monkeypatch.setattr(presets.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError, match="capture failed"):
        with presets.preset_zone(client, object(), zone_preset=4, home_preset=1):
            raise RuntimeError("capture failed")
    assert moves == [4, 1]


def test_preset_zone_retries_home(monkeypatch: pytest.MonkeyPatch) -> None:
    moves: list[int] = []

    def goto(_camera: object, index: int) -> None:
        moves.append(index)
        if index == 1 and moves.count(1) < 3:
            raise RuntimeError("temporary service failure")

    client = SimpleNamespace(goto_preset=goto)
    monkeypatch.setattr(presets.time, "sleep", lambda _seconds: None)
    with presets.preset_zone(client, object(), zone_preset=4, home_preset=1):
        pass
    assert moves == [4, 1, 1, 1]


def test_preset_request_uses_apk_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    from hikcloudstream.client import HikConnectClient
    from hikcloudstream.models import Camera

    camera = Camera(1, "Camera", "test-serial", 2, "Device")
    with HikConnectClient() as client:
        requests: list[tuple] = []

        def request(method: str, path: str, *, params: dict) -> dict:
            requests.append((method, path, params))
            return {"resultCode": "0"}

        monkeypatch.setattr(client, "request_json", request)
        client.goto_preset(camera, 3)
    assert requests == [
        (
            "POST",
            "/api/device/preset/config",
            {"subSerial": "test-serial", "channelNo": 2, "configPreset": "GOTO_PRESET", "index": 3},
        )
    ]
