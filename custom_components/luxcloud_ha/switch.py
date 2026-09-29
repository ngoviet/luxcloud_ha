"""Switch platform — 3 bit cấu hình HR[179] ghi qua cloud (Phase 2).

⚠️ ĐÂY LÀ ĐƯỜNG GHI THẬT (cloud → dongle → inverter), giống hệt app LuxCloud.
Chỉ 3 bit được tạo entity — xem `SWITCHES` bên dưới để biết vì sao
các bit còn lại CỐ Ý không có switch (tránh 2 nguồn ghi với `lxp_modbus`).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SERIAL, CONFIG_WRITE_SETTLE
from .coordinator import LuxCloudCoordinator
from .device import device_info

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class LuxSwitchDescription(SwitchEntityDescription):
    """Switch + tên bit `FUNC_*` gửi lên `remoteSet/functionControl`."""

    function_param: str


SWITCHES: tuple[LuxSwitchDescription, ...] = (
    LuxSwitchDescription(
        key="grid_peak_shaving",
        name="Grid peak shaving",
        icon="mdi:chart-timeline-variant-shimmer",
        entity_category=EntityCategory.CONFIG,
        function_param="FUNC_GRID_PEAK_SHAVING",
    ),
    LuxSwitchDescription(
        key="gen_peak_shaving",
        name="Gen peak shaving",
        icon="mdi:generator-portable",
        entity_category=EntityCategory.CONFIG,
        function_param="FUNC_GEN_PEAK_SHAVING",
    ),
    LuxSwitchDescription(
        key="active_power_limit_mode",
        name="Active power limit mode",
        icon="mdi:speedometer-slow",
        entity_category=EntityCategory.CONFIG,
        function_param="FUNC_ACTIVE_POWER_LIMIT_MODE",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: LuxCloudCoordinator = entry.runtime_data
    serial = entry.data[CONF_SERIAL]
    async_add_entities(
        LuxCloudSwitch(coordinator, serial, desc) for desc in SWITCHES
    )


class LuxCloudSwitch(CoordinatorEntity[LuxCloudCoordinator], SwitchEntity):
    """Bit cấu hình: trạng thái đọc từ cloud, ghi qua `functionControl`."""

    _attr_has_entity_name = True
    entity_description: LuxSwitchDescription

    def __init__(
        self,
        coordinator: LuxCloudCoordinator,
        serial: str,
        description: LuxSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = device_info(coordinator, serial)

    @property
    def _bits(self) -> dict | None:
        """Map bit đọc được; `None` khi cloud chưa trả (⇒ entity unavailable)."""
        bits = (self.coordinator.data or {}).get("bits")
        return bits if isinstance(bits, dict) and bits else None

    @property
    def available(self) -> bool:
        """Không có dữ liệu bit thì KHÔNG được đoán trạng thái để bấm."""
        bits = self._bits
        return (
            super().available
            and bits is not None
            and self.entity_description.function_param in bits
        )

    @property
    def is_on(self) -> bool:
        bits = self._bits or {}
        return bool(bits.get(self.entity_description.function_param))

    async def _async_write(self, enable: bool) -> None:
        param = self.entity_description.function_param
        if not await self.coordinator.api.set_config_bit(param, enable):
            raise HomeAssistantError(
                f"LuxCloud không đặt được {param} = {enable} (cloud từ chối). "
                "Xem log để biết mã lỗi."
            )
        # Cloud → dongle → inverter mất một nhịp; đọc lại ngay sẽ ra giá trị cũ.
        if CONFIG_WRITE_SETTLE:
            await asyncio.sleep(CONFIG_WRITE_SETTLE)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_write(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_write(False)
