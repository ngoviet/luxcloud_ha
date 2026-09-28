"""Binary sensor platform — cờ trạng thái của LuxCloud (Phase 1)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SERIAL
from .coordinator import LuxCloudCoordinator
from .device import device_info, dongle_device_info, parent_device_id


@dataclass(frozen=True, kw_only=True)
class LuxBinaryDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[dict], bool]
    dongle: bool = False
    attrs_fn: Callable[[dict], dict] | None = None


def _sub(key: str) -> Callable[[dict], dict]:
    return lambda d: d.get(key) or {}


def _firmware_attrs(d: dict) -> dict:
    plant = _sub("plant")(d)
    fw = _sub("firmware")(d)
    dev = plant.get("fw_version")
    latest = fw.get("latest_version")
    return {
        "device_fw_version": dev,
        "latest_fw_version": latest,
        "device_type": fw.get("device_type", ""),
        "files": [x.get("file") for x in (fw.get("items") or [])],
        "caveat": (
            "So fwVersion của inverter (api/plant/getPlantList) với version lớn nhất trong danh mục "
            "listForAppByType. Đã cross-check 2026-09-27: mã CHAA-000303 khớp ở 3 nguồn "
            "(remoteRead HOLD_FW_CODE · energyInfo.fwCode · runtime.fwCode) và catalog mới nhất là 08 "
            "trên cả 2 trục (Com/DSP). Vẫn nên xác nhận trong app trước khi nâng."
        ),
    }


BINARY_SENSORS: tuple[LuxBinaryDescription, ...] = (
    LuxBinaryDescription(
        key="dongle_lost",
        # Tên KHÔNG kèm chữ "Dongle": entity_id = slug(tên device) + slug(tên entity),
        # device đã là "LuxCloud Dongle" → để "Dongle mất kết nối" thành
        # binary_sensor.luxcloud_dongle_dongle_mat_ket_noi (đo 2026-09-28).
        name="Mất kết nối",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        dongle=True,
        is_on_fn=lambda d: bool(_sub("dongle")(d).get("lost")),
    ),
    LuxBinaryDescription(
        key="event_active",
        name="Sự cố đang hiệu lực",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda d: (str(_sub("event")(d).get("status", "CLOSE")).upper() != "CLOSE"),
        attrs_fn=lambda d: {
            k: _sub("event")(d).get(k)
            for k in ("record_id", "code", "type_text", "text", "start", "renormal")
        },
    ),
    LuxBinaryDescription(
        key="cloud_data_ok",
        name="Cloud có dữ liệu",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda d: bool(_sub("health")(d).get("cloud_ok"))
        and bool(_sub("health")(d).get("has_runtime")),
    ),
    LuxBinaryDescription(
        key="quick_task_active",
        name="Đang chạy quick charge/discharge",
        icon="mdi:battery-sync-outline",
        is_on_fn=lambda d: bool(_sub("quick")(d).get("charging"))
        or bool(_sub("quick")(d).get("discharging")),
        attrs_fn=lambda d: _sub("quick")(d),
    ),
    LuxBinaryDescription(
        key="firmware_available",
        name="Có firmware mới",
        device_class=BinarySensorDeviceClass.UPDATE,
        is_on_fn=lambda d: (
            (_sub("plant")(d).get("fw_version") is not None)
            and (_sub("firmware")(d).get("latest_version") is not None)
            and int(_sub("firmware")(d).get("latest_version", -1))
            > int(_sub("plant")(d).get("fw_version", 0))
        ),
        attrs_fn=_firmware_attrs,
    ),
    LuxBinaryDescription(
        key="off_grid",
        name="Đang chạy không lưới (isOffGrid)",
        icon="mdi:transmission-tower-off",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda d: bool(_sub("runtime")(d).get("isOffGrid")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: LuxCloudCoordinator = entry.runtime_data
    serial = entry.data[CONF_SERIAL]
    parent_id = parent_device_id(hass, serial, entry.entry_id)
    async_add_entities(
        LuxCloudBinarySensor(coordinator, serial, desc, parent_id) for desc in BINARY_SENSORS
    )


class LuxCloudBinarySensor(CoordinatorEntity[LuxCloudCoordinator], BinarySensorEntity):
    """Binary sensor đọc từ dữ liệu cloud."""

    _attr_has_entity_name = True
    entity_description: LuxBinaryDescription

    def __init__(
        self,
        coordinator: LuxCloudCoordinator,
        serial: str,
        description: LuxBinaryDescription,
        parent_device_id: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = (
            dongle_device_info(coordinator, serial, parent_device_id)
            if description.dongle
            else device_info(coordinator, serial)
        )

    @property
    def is_on(self) -> bool:
        try:
            return bool(self.entity_description.is_on_fn(self.coordinator.data or {}))
        except (TypeError, ValueError):
            return False

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data or {})
