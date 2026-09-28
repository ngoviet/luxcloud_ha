"""Sensor platform — entity ĐỌC của LuxCloud (Phase 1)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_SERIAL
from .coordinator import LuxCloudCoordinator
from .device import device_info, dongle_device_info, parent_device_id


@dataclass(frozen=True, kw_only=True)
class LuxSensorDescription(SensorEntityDescription):
    """Mô tả sensor + hàm lấy giá trị từ dữ liệu coordinator."""

    value_fn: Callable[[dict], Any]
    dongle: bool = False
    attrs_fn: Callable[[dict], dict] | None = None


def _sub(key: str) -> Callable[[dict], dict]:
    return lambda d: d.get(key) or {}


def _ts(value):
    """'2026-09-27 22:02:19' (giờ VN) -> datetime có tz cho device_class timestamp."""
    if not value:
        return None
    from datetime import datetime

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value), fmt).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        except ValueError:
            continue
    return None


def _num(value):
    """Chuỗi số ('1970.6') -> float; '--'/'' -> None."""
    try:
        return float(str(value).split()[0])
    except (ValueError, IndexError, AttributeError):
        return None


SENSORS: tuple[LuxSensorDescription, ...] = (
    # ── Dongle (device riêng) ─────────────────────────────────
    LuxSensorDescription(
        key="dongle_firmware",
        name="Firmware",
        icon="mdi:chip",
        dongle=True,
        value_fn=lambda d: _sub("dongle")(d).get("firmware") or None,
        attrs_fn=lambda d: {
            "serial": _sub("dongle")(d).get("sn", ""),
            "server_id": _sub("dongle")(d).get("server_id", ""),
        },
    ),
    LuxSensorDescription(
        key="dongle_last_report",
        name="Báo cloud lần cuối",
        icon="mdi:clock-check-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        dongle=True,
        value_fn=lambda d: _ts(_sub("dongle")(d).get("last_update")),
    ),
    LuxSensorDescription(
        key="dongle_type",
        name="Kiểu kết nối",
        icon="mdi:wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
        dongle=True,
        value_fn=lambda d: (
            _sub("dongle")(d).get("type_text") or _sub("dongle")(d).get("type") or None
        ),
    ),
    # ── Sự cố ─────────────────────────────────────────────────
    LuxSensorDescription(
        key="event_latest",
        name="Sự cố gần nhất",
        icon="mdi:history",
        value_fn=lambda d: _sub("event")(d).get("text") or None,
        attrs_fn=lambda d: {
            **{
                k: _sub("event")(d).get(k)
                for k in ("record_id", "code", "type_text", "status", "start", "renormal")
            },
            "recent": _sub("event")(d).get("recent", []),
        },
    ),
    # ── Pin (BMS qua cloud) ───────────────────────────────────
    LuxSensorDescription(
        key="bms_cycles",
        name="Chu kỳ pin",
        icon="mdi:battery-sync",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _sub("battery")(d).get("cycles"),
    ),
    LuxSensorDescription(
        key="bms_cell_delta",
        name="Lệch cell",
        icon="mdi:delta",
        native_unit_of_measurement="mV",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _sub("battery")(d).get("cell_delta_mv"),
    ),
    LuxSensorDescription(
        key="bms_cell_max_voltage",
        name="Cell cao nhất",
        icon="mdi:battery-high",
        native_unit_of_measurement="mV",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _sub("battery")(d).get("cell_max_mv"),
    ),
    LuxSensorDescription(
        key="bms_cell_min_voltage",
        name="Cell thấp nhất",
        icon="mdi:battery-low",
        native_unit_of_measurement="mV",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _sub("battery")(d).get("cell_min_mv"),
    ),
    LuxSensorDescription(
        key="bms_cell_max_temp",
        name="Nhiệt độ cell cao nhất",
        icon="mdi:thermometer-high",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _sub("battery")(d).get("cell_max_temp_c"),
    ),
    LuxSensorDescription(
        key="bms_cell_min_temp",
        name="Nhiệt độ cell thấp nhất",
        icon="mdi:thermometer-low",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _sub("battery")(d).get("cell_min_temp_c"),
    ),
    LuxSensorDescription(
        key="bms_status",
        name="Trạng thái BMS",
        icon="mdi:battery-heart-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _sub("battery")(d).get("status") or None,
    ),
    # ── Công suất thật + năng lượng 'xanh' ────────────────────
    LuxSensorDescription(
        key="ac_output",
        name="Ngõ ra AC (pinv)",
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _sub("health")(d).get("pinv"),
    ),
    LuxSensorDescription(
        key="rectifier",
        name="Rectifier (prec)",
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _sub("health")(d).get("prec"),
    ),
    LuxSensorDescription(
        key="co2_reduction",
        name="CO₂ giảm",
        icon="mdi:molecule-co2",
        native_unit_of_measurement="tấn",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _sub("green")(d).get("co2_ton"),
    ),
    LuxSensorDescription(
        key="coal_reduction",
        name="Than giảm",
        icon="mdi:mine",
        native_unit_of_measurement="kg",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _sub("green")(d).get("coal_kg"),
    ),
    LuxSensorDescription(
        key="tree_equivalent",
        name="Tương đương cây",
        icon="mdi:tree",
        native_unit_of_measurement="cây",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _sub("green")(d).get("trees"),
    ),
    # ── Firmware ──────────────────────────────────────────────
    LuxSensorDescription(
        key="inverter_fw_code",
        name="Mã firmware inverter",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _sub("health")(d).get("fw_code") or None,
        attrs_fn=lambda d: {
            "power_rating": _sub("health")(d).get("power_rating", ""),
            "plant_standard": _sub("plant")(d).get("standard", ""),
            "plant_fw_version": _sub("plant")(d).get("fw_version"),
            "hardware_version": _sub("plant")(d).get("hardware_version"),
            "protocol_version": _sub("plant")(d).get("protocol_version"),
            "machine_type": _sub("plant")(d).get("machine_type"),
        },
    ),
    LuxSensorDescription(
        key="firmware_latest",
        name="Firmware mới nhất",
        icon="mdi:package-variant-closed",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _sub("firmware")(d).get("latest_version"),
        attrs_fn=lambda d: {
            "device_type": _sub("firmware")(d).get("device_type", ""),
            "count": _sub("firmware")(d).get("count"),
            "matched": _sub("firmware")(d).get("matched"),
            "files": [x.get("file") for x in (_sub("firmware")(d).get("items") or [])],
        },
    ),
    # ── Chuỗi ngày / năm ──────────────────────────────────────
    LuxSensorDescription(
        key="day_curve",
        name="Chuỗi công suất hôm nay",
        icon="mdi:chart-bell-curve-cumulative",
        value_fn=lambda d: _sub("day_curve")(d).get("count"),
        attrs_fn=lambda d: {
            "date": _sub("day_curve")(d).get("date", ""),
            "points": _sub("day_curve")(d).get("points", []),
        },
    ),
    LuxSensorDescription(
        key="total_by_year",
        name="Tổng theo năm",
        icon="mdi:chart-bar",
        native_unit_of_measurement="kWh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: (
            (_sub("total_years")(d).get(str(dt_util.now().year)) or {}).get("pv")
        ),
        attrs_fn=lambda d: {"years": _sub("total_years")(d)},
    ),
    # ── Chẩn đoán ─────────────────────────────────────────────
    LuxSensorDescription(
        key="config_bits",
        name="Bit cấu hình HR[179] đang bật",
        icon="mdi:tune-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: sum(1 for v in _sub("bits")(d).values() if v),
        attrs_fn=lambda d: {"bits": _sub("bits")(d)},
    ),
    LuxSensorDescription(
        key="quick_state",
        name="Trạng thái quick charge/discharge",
        icon="mdi:battery-sync-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            _sub("quick")(d).get("charge_status")
            or _sub("quick")(d).get("discharge_status")
            or ("charging" if _sub("quick")(d).get("charging") else "idle")
        ),
        attrs_fn=lambda d: _sub("quick")(d),
    ),
    LuxSensorDescription(
        key="plant_total_yield",
        name="Tổng sản lượng (plant)",
        icon="mdi:solar-power-variant",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: _num(_sub("plant")(d).get("total_yielding_text")),
        attrs_fn=lambda d: {
            "plant_name": _sub("plant")(d).get("plant_name", ""),
            "today": _sub("plant")(d).get("today_yielding_text", ""),
            "status": _sub("plant")(d).get("status_text", ""),
            "model": _sub("plant")(d).get("model"),
            "battery_type": _sub("plant")(d).get("battery_type", ""),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: LuxCloudCoordinator = entry.runtime_data
    serial = entry.data[CONF_SERIAL]
    parent_id = parent_device_id(hass, serial, entry.entry_id)
    async_add_entities(
        LuxCloudSensor(coordinator, serial, desc, parent_id) for desc in SENSORS
    )


class LuxCloudSensor(CoordinatorEntity[LuxCloudCoordinator], SensorEntity):
    """Sensor đọc từ dữ liệu cloud."""

    _attr_has_entity_name = True
    entity_description: LuxSensorDescription

    def __init__(
        self,
        coordinator: LuxCloudCoordinator,
        serial: str,
        description: LuxSensorDescription,
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
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data or {})
