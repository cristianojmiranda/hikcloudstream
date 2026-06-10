"""Adapter so pyezvizapi cloud-stream helpers can use HikConnectClient."""

from __future__ import annotations

from typing import Any

import httpx
from pyezvizapi.api_endpoints import API_ENDPOINT_PAGELIST
from pyezvizapi.exceptions import PyEzvizError

from hikcloudstream.client import HikConnectClient


class HikConnectStreamAdapter:
    """Minimal EzvizClient surface for pyezvizapi.cloud_stream."""

    def __init__(self, client: HikConnectClient) -> None:
        self._client = client
        self._token: dict[str, Any] = {
            "session_id": client.session_id,
            "api_url": client.api_host,
            "service_urls": None,
        }

    def login(self) -> dict[str, Any]:
        if not self._client.session_id:
            raise PyEzvizError("Hik-Connect client is not logged in")
        self._token["session_id"] = self._client.session_id
        return self._token

    def get_service_urls(self) -> dict[str, Any]:
        service_urls = self._client.get_service_urls()
        self._token["service_urls"] = service_urls
        return service_urls

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self._client.base_url}{path}"

    def _http_request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | str | None = None,
        json_body: dict[str, Any] | None = None,
        retry_401: bool = True,
        max_retries: int = 0,
    ) -> httpx.Response:
        del retry_401, max_retries
        headers = self._client._headers()
        return self._client._http.request(
            method,
            url,
            params=params,
            data=data,
            json=json_body,
            headers=headers,
        )

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise PyEzvizError(
                f"Could not decode JSON response: {exc}\nBody: {response.text[:300]}"
            ) from exc
        if not isinstance(payload, dict):
            raise PyEzvizError("JSON response is not an object")
        return payload

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | str | None = None,
        json_body: dict[str, Any] | None = None,
        retry_401: bool = True,
        max_retries: int = 0,
    ) -> dict[str, Any]:
        response = self._http_request(
            method,
            self._url(path),
            params=params,
            data=data,
            json_body=json_body,
            retry_401=retry_401,
            max_retries=max_retries,
        )
        response.raise_for_status()
        return self._parse_json(response)

    def _api_get_pagelist(
        self,
        page_filter: str,
        json_key: str | None = None,
        group_id: int = -1,
        limit: int = 30,
        offset: int = 0,
        max_retries: int = 0,
    ) -> Any:
        del max_retries
        payload = self._request_json(
            "GET",
            API_ENDPOINT_PAGELIST,
            params={
                "groupId": group_id,
                "limit": limit,
                "offset": offset,
                "filter": page_filter,
            },
        )
        meta = payload.get("meta") or {}
        if meta.get("code") != 200:
            raise PyEzvizError(f"pagelist error: {payload}")
        if json_key:
            return payload.get(json_key)
        return payload
