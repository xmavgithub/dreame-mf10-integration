"""Tests for the standalone Dreame cloud client."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any, Self

_MODULE_PATH = (
    Path(__file__).parents[1] / "custom_components" / "dreame_mf10" / "dreame_cloud.py"
)
_SPEC = importlib.util.spec_from_file_location("dreame_cloud_under_test", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
DreameCloud = _MODULE.DreameCloud


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def json(self, *, content_type: str | None = None) -> dict[str, Any]:
        return self._payload

    async def text(self) -> str:
        return ""


class _FakeSession:
    def __init__(self, *responses: _FakeResponse) -> None:
        self._responses = list(responses)
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.requests.append((url, kwargs))
        return self._responses.pop(0)


class DreameCloudAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_preserves_reserved_username_characters(self) -> None:
        session = _FakeSession(
            _FakeResponse(
                {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "uid": "123",
                    "expires_in": 3600,
                }
            )
        )
        cloud = DreameCloud("fan+home@example.com", "password", "eu", session)

        await cloud.async_login()

        request_data = session.requests[0][1]["data"]
        self.assertIsInstance(request_data, dict)
        self.assertEqual(request_data["username"], "fan+home@example.com")
        self.assertEqual(request_data["grant_type"], "password")

    async def test_refresh_preserves_reserved_token_characters(self) -> None:
        session = _FakeSession(
            _FakeResponse(
                {
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                    "expires_in": 3600,
                }
            )
        )
        cloud = DreameCloud("user@example.com", "password", "eu", session)
        cloud._access_token = "expired-access-token"
        cloud._refresh_token = "refresh+token/with=reserved&characters"
        cloud._token_expire = 0

        await cloud._ensure_token()

        request_data = session.requests[0][1]["data"]
        self.assertIsInstance(request_data, dict)
        self.assertEqual(
            request_data["refresh_token"],
            "refresh+token/with=reserved&characters",
        )
        self.assertEqual(request_data["grant_type"], "refresh_token")


if __name__ == "__main__":
    unittest.main()
