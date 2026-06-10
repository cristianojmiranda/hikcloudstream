"""Hik-Connect REST API client."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any
from urllib.parse import urlparse

import httpx

from hikcloudstream._config import CLOUD_CAPTURE_MAX, DEVICE_FILTER, JPEG_MAGIC, RESOURCE_VTM_FILTER
from hikcloudstream.auth import check_api_meta, raise_login_error
from hikcloudstream.capture import decrypt_capture
from hikcloudstream.exceptions import ApiError, AuthenticationError, CaptureError
from hikcloudstream.models import Camera, ClientConfig, Credentials

__all__ = ["HikConnectClient", "CLOUD_CAPTURE_MAX"]


class HikConnectClient:
    """HTTP client for the Hik-Connect cloud camera API."""

    def __init__(self, config: ClientConfig | None = None) -> None:
        self.config = config or ClientConfig()
        self.base_url = self.config.api_base_url.rstrip("/")
        self.session_id: str | None = None
        self.refresh_session_id: str | None = None
        self.account: str | None = None
        self._feature_code = secrets.token_hex(16)
        self._service_urls: dict[str, Any] | None = None
        self._http = httpx.Client(
            timeout=self.config.timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> HikConnectClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def api_host(self) -> str:
        return urlparse(self.base_url).netloc

    def _headers(self, *, with_session: bool = True) -> dict[str, str]:
        headers = {
            "clientType": self.config.client_type,
            "clientVersion": self.config.client_version,
            "featureCode": self._feature_code,
            "lang": self.config.locale,
            "clientNo": self.config.client_no,
            "clientName": self.config.client_name,
            "osVersion": self.config.os_version,
            "netType": self.config.net_type,
        }
        if with_session and self.session_id:
            headers["sessionId"] = self.session_id
        return headers

    @staticmethod
    def _md5_password(password: str) -> str:
        return hashlib.md5(password.encode("utf-8")).hexdigest()

    def login(self, credentials: Credentials) -> None:
        """Authenticate and store session tokens."""
        self.account = credentials.username
        data = {
            "account": credentials.username,
            "password": self._md5_password(credentials.password),
            "featureCode": self._feature_code,
        }
        response = self._http.post(
            f"{self.base_url}/v3/users/login/v2",
            data=data,
            headers=self._headers(with_session=False),
        )
        response.raise_for_status()
        payload = response.json()

        meta = payload.get("meta") or {}
        if meta.get("code") == 1100:
            area = payload.get("loginArea") or {}
            api_domain = area.get("apiDomain")
            if not api_domain:
                raise ApiError(1100, "login redirect without apiDomain")
            self.base_url = f"https://{api_domain}"
            return self.login(credentials)

        raise_login_error(payload)
        session = payload.get("loginSession") or {}
        self.session_id = session.get("sessionId")
        self.refresh_session_id = session.get("rfSessionId")
        if not self.session_id:
            raise AuthenticationError("login succeeded but sessionId is missing")
        self._service_urls = None

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        response = self._http.request(
            method,
            url,
            params=params,
            data=data,
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    def get_service_urls(self) -> dict[str, Any]:
        if self._service_urls is not None:
            return self._service_urls
        payload = self.request_json("GET", "/v3/configurations/system/info")
        check_api_meta(payload)
        service_urls = dict(payload.get("systemConfigInfo") or {})
        self._service_urls = service_urls
        return service_urls

    def get_vtm_pagelist(self) -> dict[str, Any]:
        return self.request_json(
            "GET",
            "/v3/userdevices/v1/resources/pagelist",
            params={
                "groupId": -1,
                "limit": 50,
                "offset": 0,
                "filter": RESOURCE_VTM_FILTER,
            },
        )

    def session_sign(self) -> str:
        if not self.session_id:
            raise AuthenticationError("not logged in")
        parts = self.session_id.split(".")
        if len(parts) < 2:
            raise AuthenticationError("sessionId is not a JWT")
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode()))
        sign = claims.get("s")
        if not isinstance(sign, str) or not sign:
            raise AuthenticationError("sessionId JWT is missing VTDU sign claim")
        return sign

    def list_cameras(self) -> list[Camera]:
        cameras: list[Camera] = []
        offset = 0
        limit = 50

        while True:
            payload = self.request_json(
                "GET",
                "/v3/userdevices/v1/devices/pagelist",
                params={
                    "groupId": -1,
                    "limit": limit,
                    "offset": offset,
                    "filter": DEVICE_FILTER,
                },
            )
            check_api_meta(payload)

            for device in payload.get("deviceInfos") or []:
                serial = device.get("deviceSerial")
                device_name = device.get("name") or serial
                if not serial:
                    continue
                cameras.extend(self._cameras_for_device(str(serial), str(device_name)))

            page = payload.get("page") or {}
            if not page.get("hasNext"):
                break
            offset += limit

        return [
            Camera(
                index=index,
                name=camera.name,
                device_serial=camera.device_serial,
                channel_no=camera.channel_no,
                device_name=camera.device_name,
            )
            for index, camera in enumerate(cameras, start=1)
        ]

    def _cameras_for_device(self, device_serial: str, device_name: str) -> list[Camera]:
        payload = self.request_json(
            "GET",
            "/v3/userdevices/v1/cameras/info",
            params={"deviceSerial": device_serial},
        )
        check_api_meta(payload)

        cameras: list[Camera] = []
        for item in payload.get("cameraInfos") or []:
            channel = item.get("channelNo")
            if channel is None:
                continue
            cameras.append(
                Camera(
                    index=0,
                    name=item.get("cameraName") or f"Channel {channel}",
                    device_serial=device_serial,
                    channel_no=int(channel),
                    device_name=device_name,
                )
            )
        cameras.sort(key=lambda c: c.channel_no)
        return cameras

    def query_device_encrypt_key(self, device_serial: str, validate_code: str) -> str:
        payload = self.request_json(
            "POST",
            "/api/device/query/encryptkey",
            data={"serial": device_serial, "checkcode": validate_code},
        )
        check_api_meta(payload)
        encrypt_key = payload.get("encryptkey")
        if not encrypt_key:
            raise ApiError(0, "encrypt key response is empty")
        return str(encrypt_key)

    def capture_snapshot(
        self,
        camera: Camera,
        *,
        validate_code: str | None = None,
    ) -> bytes:
        """Return cloud snapshot JPEG bytes (352x288 max via API)."""
        raw, _pic_url = self._capture_raw(camera)
        image_bytes = decrypt_capture(raw, validate_code)
        if not image_bytes.startswith(JPEG_MAGIC):
            raise CaptureError(
                "could not decode image; provide validate_code if the device is encrypted"
            )
        return image_bytes

    def _capture_raw(self, camera: Camera) -> tuple[bytes, str | None]:
        last_error: Exception | None = None
        encrypted_payload: tuple[bytes, str] | None = None

        for is_encrypted in (0, 1):
            try:
                raw, pic_url = self._capture_once(camera, is_encrypted)
            except (ApiError, CaptureError, httpx.HTTPError) as exc:
                last_error = exc
                continue

            if raw.startswith(JPEG_MAGIC):
                return raw, pic_url

            if is_encrypted and pic_url:
                encrypted_payload = (raw, pic_url)

        if encrypted_payload:
            return encrypted_payload[0], encrypted_payload[1]

        raise CaptureError(f"capture failed: {last_error or 'no image returned'}")

    def _capture_once(self, camera: Camera, is_encrypted: int) -> tuple[bytes, str | None]:
        response = self._http.put(
            f"{self.base_url}/v3/devices/security/capture",
            params={
                "deviceSerial": camera.device_serial,
                "channelNo": camera.channel_no,
                "isEncrypted": is_encrypted,
            },
            headers=self._headers(),
        )
        response.raise_for_status()
        payload = response.json()
        check_api_meta(payload)

        capture_info = payload.get("captureInfo") or {}
        pic_url = capture_info.get("picUrl")
        if not pic_url:
            raise CaptureError("capture response has no picUrl")

        image_response = self._http.get(str(pic_url))
        image_response.raise_for_status()
        raw = image_response.content
        if not raw:
            raise CaptureError("downloaded image is empty")
        return raw, str(pic_url)
