"""Async Dreame Cloud API client for the MF10 integration.

Adapted from CodyJon/dreame-ap10-integration (sync `requests` based) to async
aiohttp for native Home Assistant compatibility.

Endpoint shape (per region):
    https://{region}.iot.dreame.tech:13267

Auth flow:
    POST /dreame-auth/oauth/token      OAuth2 password / refresh_token grant
    POST /dreame-user-iot/iotuserbind/device/listV2   device list
    POST /dreame-iot-com/device/sendCommand          MiOT-style RPC
        methods: get_properties, set_properties, action

Security:
    - Passwords are MD5(password + DREAME_SALT) before being sent.
    - access_token / refresh_token are kept in memory only.
    - NOTHING sensitive is ever logged (no tokens, no passwords, no headers).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Static constants that identify the Dreamehome app to the cloud. These are NOT
# secrets — they are the public app identity sent by every Dreamehome client.
_DREAME_SALT = "RAylYC%fmSKp7%Tq"
_DREAME_USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
_DREAME_AUTH_BASIC = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
_DREAME_TENANT_ID = "000000"
_DREAME_RLC = "1c80b3787b2266776bcd"  # required header for cn region

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15)
_TOKEN_REFRESH_MARGIN_S = 120


class DreameAuthError(Exception):
    """Authentication with Dreame Cloud failed (invalid credentials, etc.)."""


class DreameConnectionError(Exception):
    """Network / transport error talking to Dreame Cloud."""


class DreameApiError(Exception):
    """Dreame Cloud returned an unexpected response."""


class DreameCloud:
    """Async client for the Dreame Cloud API."""

    def __init__(
        self,
        username: str,
        password: str,
        region: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._username = username
        self._password = password
        self._region = region
        self._session = session

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._uid: str | None = None
        self._tenant_id: str = _DREAME_TENANT_ID
        self._token_expire: float | None = None
        self._lock = asyncio.Lock()

    # ----- public API ----------------------------------------------------

    @property
    def api_url(self) -> str:
        return f"https://{self._region}.iot.dreame.tech:13267"

    async def async_login(self) -> None:
        """Perform initial login. Raises on failure."""
        await self._login()

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Return the list of devices bound to the account."""
        await self._ensure_token()
        url = f"{self.api_url}/dreame-user-iot/iotuserbind/device/listV2"
        result = await self._post_json(url, json={}, retry_on_401=True)
        try:
            return result["data"]["page"]["records"] or []
        except (KeyError, TypeError) as err:
            raise DreameApiError(f"Unexpected devices payload shape: {err}") from err

    async def async_get_properties(
        self,
        did: str | int,
        properties: list[dict[str, int]],
        host: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read MiOT properties. Returns the raw `result` list from Dreame.

        `host` is the value of `bindDomain` from the device record returned
        by `async_get_devices`. When set, the command URL gets a per-bind
        suffix (e.g. `/dreame-iot-com-eu1/...`) — without it the EU backend
        responds with HTTP 404.
        """
        params = [
            {"did": str(did), "siid": p["siid"], "piid": p["piid"]} for p in properties
        ]
        return await self._send_command(did, "get_properties", params, host=host) or []

    async def async_set_properties(
        self,
        did: str | int,
        properties: list[dict[str, Any]],
        host: str | None = None,
    ) -> list[dict[str, Any]]:
        """Write MiOT properties. Each prop must include siid, piid, value."""
        params = [
            {
                "did": str(did),
                "siid": p["siid"],
                "piid": p["piid"],
                "value": p["value"],
            }
            for p in properties
        ]
        return await self._send_command(did, "set_properties", params, host=host) or []

    async def async_call_action(
        self,
        did: str | int,
        siid: int,
        aiid: int,
        params: list | None = None,
        host: str | None = None,
    ) -> dict[str, Any] | None:
        """Invoke a MiOT action."""
        payload = {"did": str(did), "siid": siid, "aiid": aiid, "in": params or []}
        return await self._send_command(did, "action", payload, host=host)

    # ----- internals -----------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        if not self._access_token:
            raise DreameAuthError("No access token; login first")
        # Dreame backend wants the STATIC app-level Authorization header,
        # plus the user access token in a dedicated `Dreame-Auth` header.
        # Using `Authorization: Bearer <token>` returns HTTP 401 "Missing token".
        headers = {
            "User-Agent": _DREAME_USER_AGENT,
            "Authorization": _DREAME_AUTH_BASIC,
            "Dreame-Auth": self._access_token,
            "Tenant-Id": self._tenant_id,
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        if self._region == "cn":
            headers["Dreame-Rlc"] = _DREAME_RLC
        return headers

    async def _ensure_token(self) -> None:
        async with self._lock:
            if self._access_token is None:
                await self._login_locked()
                return
            if (
                self._token_expire is not None
                and time.time() > self._token_expire - _TOKEN_REFRESH_MARGIN_S
            ):
                await self._refresh_locked()

    async def _login(self) -> None:
        async with self._lock:
            await self._login_locked()

    async def _login_locked(self) -> None:
        url = f"{self.api_url}/dreame-auth/oauth/token"
        pw_hash = hashlib.md5(
            (self._password + _DREAME_SALT).encode("utf-8")
        ).hexdigest()
        # Pass a mapping so aiohttp applies application/x-www-form-urlencoded
        # escaping. Building this body manually corrupts usernames containing
        # characters such as "+" or "&".
        data = {
            "platform": "IOS",
            "scope": "all",
            "grant_type": "password",
            "username": self._username,
            "password": pw_hash,
            "type": "account",
        }
        headers = {
            "User-Agent": _DREAME_USER_AGENT,
            "Authorization": _DREAME_AUTH_BASIC,
            "Tenant-Id": _DREAME_TENANT_ID,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
        }
        if self._region == "cn":
            headers["Dreame-Rlc"] = _DREAME_RLC

        try:
            async with self._session.post(
                url, headers=headers, data=data, timeout=_DEFAULT_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    if resp.status in (400, 401, 403):
                        raise DreameAuthError(
                            f"Login rejected (HTTP {resp.status}): {body[:200]}"
                        )
                    raise DreameApiError(
                        f"Login failed (HTTP {resp.status}): {body[:200]}"
                    )
                result = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise DreameConnectionError(f"Cannot reach Dreame Cloud: {err}") from err
        except asyncio.TimeoutError as err:
            raise DreameConnectionError("Timeout talking to Dreame Cloud") from err

        if "access_token" not in result:
            # Do NOT log result wholesale — may include error context with PII.
            raise DreameAuthError("Login response missing access_token")

        self._access_token = result["access_token"]
        self._refresh_token = result.get("refresh_token")
        self._uid = result.get("uid")
        self._tenant_id = result.get("tenant_id") or _DREAME_TENANT_ID
        self._token_expire = time.time() + int(result.get("expires_in", 3600))
        _LOGGER.debug("Dreame login OK (region=%s)", self._region)
        if self._region == "ru":
            _LOGGER.info(
                "Dreame region 'ru' is unverified by upstream — endpoint may not exist; "
                "if you see connectivity issues, try a different region"
            )

    async def _refresh_locked(self) -> None:
        if not self._refresh_token:
            await self._login_locked()
            return

        url = f"{self.api_url}/dreame-auth/oauth/token"
        data = {
            "platform": "IOS",
            "scope": "all",
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }
        headers = {
            "User-Agent": _DREAME_USER_AGENT,
            "Authorization": _DREAME_AUTH_BASIC,
            "Tenant-Id": self._tenant_id,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            async with self._session.post(
                url, headers=headers, data=data, timeout=_DEFAULT_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("Token refresh non-200 (%s), falling back to login", resp.status)
                    await self._login_locked()
                    return
                result = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("Token refresh failed (%s), retrying login", type(err).__name__)
            await self._login_locked()
            return

        if "access_token" not in result:
            await self._login_locked()
            return
        self._access_token = result["access_token"]
        self._refresh_token = result.get("refresh_token") or self._refresh_token
        self._token_expire = time.time() + int(result.get("expires_in", 3600))

    async def _send_command(
        self,
        did: str | int,
        method: str,
        params: Any,
        *,
        host: str | None = None,
    ) -> Any:
        await self._ensure_token()
        # `bindDomain` from listV2 routes the command to the bind cluster.
        # Example: bindDomain="eu1.iot.dreame.tech" → path suffix "-eu1".
        host_prefix = f"-{host.split('.')[0]}" if host else ""
        url = f"{self.api_url}/dreame-iot-com{host_prefix}/device/sendCommand"
        payload = {
            "did": str(did),
            "id": 1,
            "data": {"did": str(did), "id": 1, "method": method, "params": params},
        }
        result = await self._post_json(url, json=payload, retry_on_401=True)
        if result.get("code") != 0:
            # code=80001 ("设备可能不在线，指令发送超时") = device unreachable for
            # write commands. get_properties still works because the server returns
            # cached values; set_properties/action require the device to be online
            # and acknowledge within the server-side timeout.
            _LOGGER.debug("Command %s failed: code=%s msg=%s", method, result.get("code"), result.get("msg", ""))
            raise DreameApiError(
                f"Command {method} failed: code={result.get('code')}"
            )
        data = result.get("data") or {}
        if "result" in data:
            return data["result"]
        if result.get("success"):
            return {"code": 0}
        return None

    async def _post_json(
        self,
        url: str,
        *,
        json: dict[str, Any],
        retry_on_401: bool,
    ) -> dict[str, Any]:
        try:
            async with self._session.post(
                url,
                headers=self._auth_headers(),
                json=json,
                timeout=_DEFAULT_TIMEOUT,
            ) as resp:
                if resp.status == 401 and retry_on_401:
                    await self._login()
                    return await self._post_json(url, json=json, retry_on_401=False)
                if resp.status != 200:
                    body = await resp.text()
                    raise DreameApiError(
                        f"HTTP {resp.status} from {url}: {body[:200]}"
                    )
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise DreameConnectionError(str(err)) from err
        except asyncio.TimeoutError as err:
            raise DreameConnectionError(f"Timeout calling {url}") from err
