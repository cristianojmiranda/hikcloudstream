"""VTDU stream token providers for VTM live sessions."""

from __future__ import annotations

from urllib.parse import urlparse

from pyezvizapi.api_endpoints import API_ENDPOINT_VTDU_TOKEN_V2

from hikcloudstream.client import _trusted_cloud_origin
from hikcloudstream.exceptions import AuthenticationError, TokenError
from hikcloudstream.stream.adapter import HikConnectStreamAdapter


def get_vtdu_tokens(adapter: HikConnectStreamAdapter, *, count: int = 5) -> list[str]:
    """Fetch VTDU stream tokens required by the VTM live stream protocol."""
    session_id = adapter._client.session_id
    if not session_id:
        raise AuthenticationError("not logged in")

    try:
        response = adapter._client._http.post(
            f"{adapter._client.base_url}/api/user/token/get",
            data={"sessionId": session_id, "count": count},
            headers=adapter._client._headers(),
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        tokens = payload.get("tokenArray") or payload.get("tokens")
        if isinstance(tokens, list) and tokens:
            return [str(token) for token in tokens]
        if payload.get("resultCode") not in (None, "0", 0):
            raise TokenError("Hik-Connect token API rejected the request")
    except Exception:
        pass

    sign = adapter._client.session_sign()

    for auth_base in _auth_base_candidates(adapter):
        try:
            response = adapter._client._http.get(
                f"{auth_base}{API_ENDPOINT_VTDU_TOKEN_V2}",
                params={"ssid": session_id, "sign": sign},
                headers=adapter._client._headers(),
                timeout=20.0,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("retcode") not in (0, "0"):
                raise TokenError("VTDU token API rejected the request")
            tokens = payload.get("tokens")
            if not isinstance(tokens, list) or not tokens:
                raise TokenError("VTDU token API returned no tokens")
            return [str(token) for token in tokens]
        except Exception:
            continue

    raise TokenError(
        "could not obtain VTDU stream token; live stream requires auth service "
        "access"
    )


def _auth_base_candidates(adapter: HikConnectStreamAdapter) -> list[str]:
    service_urls = adapter.get_service_urls()
    candidates: list[str] = []

    auth_addr = str(service_urls.get("authAddr") or "").strip()
    if auth_addr and auth_addr.lower() not in {"https://null", "null", "none", ""}:
        try:
            candidates.append(_trusted_cloud_origin(auth_addr))
        except AuthenticationError:
            pass

    api_host = adapter._client.api_host
    if api_host.startswith("api") and api_host.endswith(".hik-connect.com"):
        region = api_host[3 : -len(".hik-connect.com")]
        candidates.extend(
            [
                f"https://{region}auth.hik-connect.com",
                f"https://auth{region}.hik-connect.com",
                f"https://{region}auth.ezvizlife.com",
            ]
        )
        if region.startswith("isa") or region.endswith("sa"):
            candidates.extend(
                [
                    "https://sacas.ezvizlife.com",
                    "https://authsa.ezvizlife.com",
                    "https://sauth.ezvizlife.com",
                ]
            )

    parsed = urlparse(adapter._client.base_url)
    host = parsed.hostname or ""
    if host.startswith("apii") and host.endswith(".ezvizlife.com"):
        region = host[4 : -len(".ezvizlife.com")]
        if region:
            candidates.append(f"https://{region}auth.ezvizlife.com")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped
