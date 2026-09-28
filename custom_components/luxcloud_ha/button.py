"""Button platform — quick charge / quick discharge qua cloud (Phase 2).

Bốn nút tường minh (start/stop × charge/discharge) thay vì 2 nút toggle: đây là
lệnh GHI xuống inverter, `start`/`stop` là hai endpoint khác nhau nên nói thẳng
ra an toàn hơn là để nút tự đoán ý.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SERIAL,
    CONFIG_WRITE_SETTLE,
    QUICK_CHARGE,
    QUICK_DISCHARGE,
    QUICK_OPS,
)
from .coordinator import LuxCloudCoordinator
from .device import device_info

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class LuxButtonDescription(ButtonEntityDescription):
    """Nút + endpoint `{action}/{op}` gửi lên cloud."""

    action: str
    op: str


BUTTONS: tuple[LuxButtonDescription, ...] = (
    LuxButtonDescription(
        key="quick_charge_start",
        name="Quick charge start",
        icon="mdi:battery-charging-high",
        action=QUICK_CHARGE,
        op="start",
    ),
    LuxButtonDescription(
        key="quick_charge_stop",
        name="Quick charge stop",
        icon="mdi:battery-charging-outline",
        action=QUICK_CHARGE,
        op="stop",
    ),
    LuxButtonDescription(
        key="quick_discharge_start",
        name="Quick discharge start",
        icon="mdi:battery-arrow-down",
        action=QUICK_DISCHARGE,
        op="start",
    ),
    LuxButtonDescription(
        key="quick_discharge_stop",
        name="Quick discharge stop",
        icon="mdi:battery-arrow-up-outline",
        action=QUICK_DISCHARGE,
        op="stop",
    ),
)


def _is_running(coordinator: LuxCloudCoordinator, action: str) -> bool:
    quick = (coordinator.data or {}).get("quick") or {}
    return bool(quick.get("charging") if action == QUICK_CHARGE else quick.get("discharging"))


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: LuxCloudCoordinator = entry.runtime_data
    serial = entry.data[CONF_SERIAL]
    async_add_entities(
        LuxCloudQuickButton(coordinator, serial, desc) for desc in BUTTONS
    )


class LuxCloudQuickButton(CoordinatorEntity[LuxCloudCoordinator], ButtonEntity):
    """Nút start/stop quick charge hoặc quick discharge."""

    _attr_has_entity_name = True
    entity_description: LuxButtonDescription

    def __init__(
        self,
        coordinator: LuxCloudCoordinator,
        serial: str,
        description: LuxButtonDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = device_info(coordinator, serial)

    @property
    def available(self) -> bool:
        """`start` chỉ hiện khi task đang không chạy; `stop` chỉ khi đang chạy."""
        if not super().available:
            return False
        running = _is_running(self.coordinator, self.entity_description.action)
        return running if self.entity_description.op == "stop" else not running

    async def async_press(self) -> None:
        desc = self.entity_description
        if not await self.coordinator.api.set_quick(desc.action, desc.op):
            raise HomeAssistantError(
                f"LuxCloud không gửi được {desc.action}/{desc.op} (cloud từ chối). "
                "Xem log để biết mã lỗi."
            )
        if CONFIG_WRITE_SETTLE:
            await asyncio.sleep(CONFIG_WRITE_SETTLE)
        await self.coordinator.async_request_refresh()
