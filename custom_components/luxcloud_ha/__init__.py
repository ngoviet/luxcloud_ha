"""Setup integration LuxCloud (Phase 1 — chỉ đọc)."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LuxCloudApi, LuxCloudApiError, LuxCloudAuthError
from .const import (
    CONF_ACCOUNT,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    REGIONS,
)
from .coordinator import LuxCloudCoordinator
from .device import device_info

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

LuxCloudConfigEntry = ConfigEntry[LuxCloudCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LuxCloudConfigEntry) -> bool:
    """Tạo coordinator + forward platforms."""
    session = async_get_clientsession(hass)
    region = str(entry.data.get(CONF_REGION, DEFAULT_REGION)).lower()
    api = LuxCloudApi(
        session,
        REGIONS.get(region, REGIONS[DEFAULT_REGION]),
        entry.data[CONF_ACCOUNT],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_SERIAL],
    )
    try:
        await api.login()
    except LuxCloudAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except LuxCloudApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    coordinator = LuxCloudCoordinator(hass, api, entry, interval)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Đăng ký device inverter TRƯỚC khi load platform: device dongle cần `via_device_id`
    # trỏ vào id thật của device này (HA đã deprecate key `via_device` từ 2027.8).
    serial = entry.data[CONF_SERIAL]
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **device_info(coordinator, serial)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info(
        "LuxCloud ready: %s (plant %s, dongle %s)",
        serial,
        (coordinator.data.get("plant") or {}).get("plant_id"),
        (coordinator.data.get("dongle") or {}).get("sn"),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LuxCloudConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: LuxCloudConfigEntry) -> None:
    """Đổi options → reload entry (KHÔNG cần restart HA)."""
    await hass.config_entries.async_reload(entry.entry_id)
