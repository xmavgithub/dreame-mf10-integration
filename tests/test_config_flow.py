"""Focused tests for Dreame MF10 reauthentication."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import patch


class _ConfigFlow:
    """Small Home Assistant ConfigFlow stand-in for unit testing."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__()

    def _get_reauth_entry(self) -> SimpleNamespace:
        return self.reauth_entry

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    def async_update_reload_and_abort(
        self, entry: SimpleNamespace, **kwargs: Any
    ) -> dict[str, Any]:
        self.update_calls.append((entry, kwargs))
        return {"type": "abort", "reason": "reauth_successful"}


def _install_home_assistant_stubs() -> dict[str, ModuleType | None]:
    module_names = (
        "homeassistant",
        "homeassistant.config_entries",
        "homeassistant.const",
        "homeassistant.helpers",
        "homeassistant.helpers.aiohttp_client",
    )
    original_modules = {name: sys.modules.get(name) for name in module_names}

    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.ConfigFlow = _ConfigFlow
    config_entries.ConfigFlowResult = dict

    const = ModuleType("homeassistant.const")
    const.CONF_PASSWORD = "password"
    const.CONF_USERNAME = "username"

    helpers = ModuleType("homeassistant.helpers")
    aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda hass: object()

    homeassistant.config_entries = config_entries
    homeassistant.helpers = helpers
    helpers.aiohttp_client = aiohttp_client
    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.config_entries": config_entries,
            "homeassistant.const": const,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.aiohttp_client": aiohttp_client,
        }
    )
    return original_modules


def _load_integration_module(name: str) -> ModuleType:
    integration_path = (
        Path(__file__).parents[1] / "custom_components" / "dreame_mf10"
    )
    package_name = "dreame_mf10_under_test"
    if package_name not in sys.modules:
        package = ModuleType(package_name)
        package.__path__ = [str(integration_path)]
        sys.modules[package_name] = package

    module_name = f"{package_name}.{name}"
    spec = importlib.util.spec_from_file_location(
        module_name, integration_path / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_ORIGINAL_MODULES = _install_home_assistant_stubs()
try:
    _load_integration_module("const")
    _load_integration_module("dreame_cloud")
    CONFIG_FLOW = _load_integration_module("config_flow")
finally:
    for _name, _module in _ORIGINAL_MODULES.items():
        if _module is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _module


class _CloudStub:
    devices: ClassVar[list[dict[str, Any]]] = []
    api_error = False

    def __init__(self, **kwargs: Any) -> None:
        pass

    async def async_login(self) -> None:
        pass

    async def async_get_devices(self) -> list[dict[str, Any]]:
        if self.api_error:
            raise CONFIG_FLOW.DreameApiError("cloud response failed")
        return self.devices


class DreameConfigFlowReauthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.entry_data = {
            "username": "old@example.com",
            "password": "old-password",
            "region": "eu",
            "did": "configured-device",
        }
        self.entry = SimpleNamespace(data=self.entry_data.copy())
        self.flow = CONFIG_FLOW.DreameMF10ConfigFlow()
        self.flow.hass = object()
        self.flow.reauth_entry = self.entry
        self.flow.update_calls = []

    async def test_reauth_rejects_account_without_configured_device(self) -> None:
        class MissingDeviceCloud(_CloudStub):
            devices: ClassVar[list[dict[str, Any]]] = [
                {"did": "different-device"}
            ]

        with patch.object(CONFIG_FLOW, "DreameCloud", MissingDeviceCloud):
            result = await self.flow.async_step_reauth_confirm(
                {"username": "new@example.com", "password": "new-password"}
            )

        self.assertEqual(result["errors"], {"base": "no_supported_devices"})
        self.assertEqual(self.entry.data, self.entry_data)
        self.assertEqual(self.flow.update_calls, [])

    async def test_reauth_reports_api_error_as_unknown(self) -> None:
        class FailingCloud(_CloudStub):
            api_error = True

        with (
            patch.object(CONFIG_FLOW, "DreameCloud", FailingCloud),
            patch.object(CONFIG_FLOW._LOGGER, "exception"),
        ):
            result = await self.flow.async_step_reauth_confirm(
                {"username": "new@example.com", "password": "new-password"}
            )

        self.assertEqual(result["errors"], {"base": "unknown"})
        self.assertEqual(self.entry.data, self.entry_data)
        self.assertEqual(self.flow.update_calls, [])

    async def test_reauth_updates_credentials_after_device_validation(self) -> None:
        class MatchingDeviceCloud(_CloudStub):
            devices: ClassVar[list[dict[str, Any]]] = [
                {"did": "configured-device"}
            ]

        user_input = {
            "username": "new@example.com",
            "password": "new-password",
        }
        with patch.object(CONFIG_FLOW, "DreameCloud", MatchingDeviceCloud):
            result = await self.flow.async_step_reauth_confirm(user_input)

        self.assertEqual(
            result, {"type": "abort", "reason": "reauth_successful"}
        )
        self.assertEqual(len(self.flow.update_calls), 1)
        updated_entry, update_kwargs = self.flow.update_calls[0]
        self.assertIs(updated_entry, self.entry)
        self.assertEqual(update_kwargs, {"data_updates": user_input})


if __name__ == "__main__":
    unittest.main()
