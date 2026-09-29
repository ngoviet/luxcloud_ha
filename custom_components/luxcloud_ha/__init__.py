"""Setup integration LuxCloud (Phase 2 — có đường GHI qua cloud)."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_extract_config_entry_ids

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

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
]

LuxCloudConfigEntry = ConfigEntry[LuxCloudCoordinator]

SERVICE_SET_BIT = "set_bit"
ATTR_FUNCTION = "function"
ATTR_ENABLE = "enable"

TARGET_KEYS = ("device_id", "entity_id", "area_id", "floor_id", "label_id")

SET_BIT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_FUNCTION): vol.All(str, vol.Match(r"^FUNC_[A-Z0-9_]+$")),
        vol.Required(ATTR_ENABLE): cv.boolean,
    },
    # Cho phép các khoá target của HA (device_id/entity_id/area_id…) đi qua —
    # đúng cách HA core làm cho service nhắm tới thiết bị; chúng được đọc bằng
    # `async_extract_config_entry_ids`, không phải tham số của service.
    extra=vol.ALLOW_EXTRA,
)


async def _async_entries_for_call(hass: HomeAssistant, call: ServiceCall) -> list:
    """Entry mà service call nhắm tới.

    Có target (device/entity/area) → các entry tương ứng. Không target → chỉ dùng
    khi đúng MỘT inverter đang chạy; nhiều inverter mà không target thì báo lỗi
    thay vì đoán bừa (ghi nhầm inverter là hỏng thật).
    """
    entry_ids = await async_extract_config_entry_ids(call)
    entries = [
        entry
        for entry_id in entry_ids
        if (entry := hass.config_entries.async_get_entry(entry_id)) is not None
        and entry.domain == DOMAIN
    ]
    if entries:
        return entries

    if any(key in call.data for key in TARGET_KEYS):
        raise HomeAssistantError(
            "Không có inverter LuxCloud nào khớp với target được chọn."
        )

    entries = list(hass.config_entries.async_loaded_entries(DOMAIN))
    if len(entries) == 1:
        return entries
    raise HomeAssistantError(
        "Có nhiều inverter LuxCloud — hãy chọn thiết bị (target) cho service này."
        if entries
        else "Không có inverter LuxCloud nào đang chạy."
    )


async def _async_handle_set_bit(hass: HomeAssistant, call: ServiceCall) -> None:
    """Bật/tắt một bit cấu hình HR[179] qua cloud."""
    function: str = call.data[ATTR_FUNCTION]
    enable: bool = call.data[ATTR_ENABLE]
    for entry in await _async_entries_for_call(hass, call):
        coordinator: LuxCloudCoordinator = entry.runtime_data
        if not await coordinator.api.set_config_bit(function, enable):
            raise HomeAssistantError(
                f"LuxCloud không đặt được {function} = {enable} trên {entry.title} (cloud từ chối)."
            )
        await coordinator.async_request_refresh()
    _LOGGER.info("luxcloud: service set_bit %s=%s xong", function, enable)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Đăng ký service `set_bit` (một lần cho cả domain)."""

    async def _handle(call: ServiceCall) -> None:
        await _async_handle_set_bit(hass, call)

    hass.services.async_register(DOMAIN, SERVICE_SET_BIT, _handle, schema=SET_BIT_SCHEMA)
    return True



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
