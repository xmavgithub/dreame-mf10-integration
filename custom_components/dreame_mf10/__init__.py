"""The Dreame MF10 integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_REGION, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, PLATFORMS
from .coordinator import MF10Coordinator
from .dreame_cloud import (
    DreameApiError,
    DreameAuthError,
    DreameCloud,
    DreameConnectionError,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Dreame MF10 config entry."""
    session = async_get_clientsession(hass)
    cloud = DreameCloud(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        region=entry.data.get(CONF_REGION, "eu"),
        session=session,
    )

    try:
        await cloud.async_login()
        devices = await cloud.async_get_devices()
    except DreameAuthError as err:
        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
    except (DreameConnectionError, DreameApiError) as err:
        raise ConfigEntryNotReady(f"Dreame Cloud setup failed: {err}") from err

    did = entry.data["did"]
    device = next((d for d in devices if str(d.get("did")) == did), None)
    if device is None:
        raise ConfigEntryNotReady(f"Device {did} not found in account device list")

    host = device.get("bindDomain")
    _LOGGER.debug("Device %s bindDomain=%s", did, host)

    coordinator = MF10Coordinator(hass, cloud, did, host)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Dreame MF10 config entry."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return ok
