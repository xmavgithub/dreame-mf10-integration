"""Config flow for the Dreame MF10 integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_REGION,
    DEFAULT_REGION,
    DOMAIN,
    REGION_OPTIONS,
    SUPPORTED_MODELS,
)
from .dreame_cloud import (
    DreameApiError,
    DreameAuthError,
    DreameCloud,
    DreameConnectionError,
)

_LOGGER = logging.getLogger(__name__)

_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION, default=DEFAULT_REGION): vol.In(REGION_OPTIONS),
    }
)


class DreameMF10ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Dreame MF10 cloud-based config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._candidate_devices: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = DreameCloud(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                region=user_input[CONF_REGION],
                session=session,
            )
            try:
                await client.async_login()
                devices = await client.async_get_devices()
            except DreameAuthError:
                errors["base"] = "invalid_auth"
            except DreameConnectionError:
                errors["base"] = "cannot_connect"
            except DreameApiError:
                _LOGGER.exception("Dreame API error during config flow")
                errors["base"] = "unknown"
            except Exception:  # noqa: BLE001 - guardrail for unexpected errors
                _LOGGER.exception("Unexpected error during Dreame MF10 setup")
                errors["base"] = "unknown"
            else:
                supported = [
                    d for d in devices if d.get("model") in SUPPORTED_MODELS
                ]
                if not supported:
                    errors["base"] = "no_supported_devices"
                else:
                    self._credentials = user_input
                    self._candidate_devices = supported
                    if len(supported) == 1:
                        return await self._create_entry(supported[0])
                    return await self.async_step_pick_device()

        return self.async_show_form(
            step_id="user", data_schema=_USER_SCHEMA, errors=errors
        )

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """When the account has more than one MF10, ask the user to pick."""
        options = {
            str(d.get("did")): f"{d.get('name') or d.get('model')} ({d.get('did')})"
            for d in self._candidate_devices
        }

        if user_input is not None:
            did = user_input["did"]
            device = next(
                (d for d in self._candidate_devices if str(d.get("did")) == did),
                None,
            )
            if device is None:
                return self.async_abort(reason="no_supported_devices")
            return await self._create_entry(device)

        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema({vol.Required("did"): vol.In(options)}),
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = DreameCloud(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                region=reauth_entry.data.get(CONF_REGION, DEFAULT_REGION),
                session=session,
            )
            try:
                await client.async_login()
                devices = await client.async_get_devices()
            except DreameAuthError:
                errors["base"] = "invalid_auth"
            except DreameConnectionError:
                errors["base"] = "cannot_connect"
            except DreameApiError:
                _LOGGER.exception("Dreame API error during reauth")
                errors["base"] = "unknown"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Dreame MF10 reauth")
                errors["base"] = "unknown"
            else:
                configured_did = str(reauth_entry.data["did"])
                if not any(
                    str(device.get("did")) == configured_did for device in devices
                ):
                    errors["base"] = "no_supported_devices"
                else:
                    return self.async_update_reload_and_abort(
                        reauth_entry,
                        data_updates={
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME, default=reauth_entry.data[CONF_USERNAME]
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def _create_entry(self, device: dict[str, Any]) -> ConfigFlowResult:
        did = str(device.get("did"))
        await self.async_set_unique_id(did)
        self._abort_if_unique_id_configured()
        title = device.get("name") or f"Dreame MF10 {did}"
        data = {
            **self._credentials,
            "did": did,
            "model": device.get("model"),
            "mac": device.get("mac"),
        }
        return self.async_create_entry(title=title, data=data)
