"""Sensor platform — entity ĐỌC của LuxCloud (Phase 1)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
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
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
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
    # Chỉ dùng với `state_class=TOTAL`: mốc đầu kỳ để thống kê hiểu cú về 0 là sang kỳ mới.
    last_reset_fn: Callable[[dict], datetime | None] | None = None


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


def _opt_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _scaled(value, divisor: float, digits: int):
    """Số thô của runtime (vacr ×10, fac ×100) → đơn vị thật; thiếu/sai ⇒ None."""
    try:
        return round(float(value) / divisor, digits)
    except (TypeError, ValueError):
        return None


def _num(value):
    """Chuỗi số ('1970.6') -> float; '--'/'' -> None."""
    try:
        return float(str(value).split()[0])
    except (ValueError, IndexError, AttributeError):
        return None


_KWH_SCALE = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0, "gwh": 1_000_000.0}


def _kwh(value):
    """'1997.4 kWh' -> 1997.4 ; '2.1 MWh' -> 2100.0 ; '--' -> None.

    Cloud trả text kèm đơn vị; khi sản lượng lớn nó có thể đổi sang MWh. Bỏ
    đơn vị như `_num` thì sensor (đơn vị kWh) tụt từ ~2000 xuống ~2, làm hỏng
    thống kê năng lượng.
    """
    number = _num(value)
    if number is None:
        return None
    parts = str(value).split()
    unit = parts[1].lower() if len(parts) > 1 else "kwh"
    return round(number * _KWH_SCALE.get(unit, 1.0), 3)


def _period(part: str, metric: str) -> Callable[[dict], Any]:
    return lambda d: (_sub("periods")(d).get(part) or {}).get(metric)


def _local_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=dt_util.DEFAULT_TIME_ZONE)


def _period_reset(part: str) -> Callable[[dict], datetime | None]:
    """Đầu kỳ hoá đơn (month) hoặc 1/1 (year), 00:00 giờ địa phương."""

    def _fn(d: dict) -> datetime | None:
        info = _sub("periods")(d).get(part) or {}
        try:
            if part == "month":
                return _local_midnight(date.fromisoformat(info["start"]))
            return _local_midnight(date(int(info["year"]), 1, 1))
        except (KeyError, TypeError, ValueError):
            return None

    return _fn


def _period_attrs(part: str) -> Callable[[dict], dict]:
    keys = ("start", "end") if part == "month" else ("year",)
    return lambda d: {k: (_sub("periods")(d).get(part) or {}).get(k) for k in keys}


# (khoá, tên, icon) — năng lượng theo kỳ hoá đơn / năm từ monthColumn & yearColumn.
_PERIOD_METRICS = (
    ("pv", "PV", "mdi:solar-power"),
    ("grid_import", "Mua lưới", "mdi:transmission-tower-import"),
    ("charge", "Sạc pin", "mdi:battery-plus-variant"),
    ("discharge", "Xả pin", "mdi:battery-minus-variant"),
    ("eps", "EPS", "mdi:home-import-outline"),
    ("consumption", "Tiêu thụ", "mdi:home-lightning-bolt"),
)
_PERIODS = (("month", "tháng"), ("year", "năm"))
_TARIFF_NOTE = (
    "Tiền điện nếu không có NLMT (theo tổng tiêu thụ) trừ tiền điện thực trả (theo điện mua "
    "lưới); giá bậc thang EVN QĐ 4495/QĐ-BCT + VAT 8%."
)


def _savings_attrs(part: str) -> Callable[[dict], dict]:
    return lambda d: {**_period_attrs(part)(d), "cach_tinh": _TARIFF_NOTE}


PERIOD_SENSORS: tuple[LuxSensorDescription, ...] = (
    *(
        LuxSensorDescription(
            key=f"{part}_{metric}",
            name=f"{label} {suffix}",
            icon=icon,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL,
            value_fn=_period(part, metric),
            last_reset_fn=_period_reset(part),
            attrs_fn=_period_attrs(part),
        )
        for part, suffix in _PERIODS
        for metric, label, icon in _PERIOD_METRICS
    ),
    *(
        LuxSensorDescription(
            key=f"{part}_savings",
            name=f"Tiết kiệm {suffix}",
            icon="mdi:cash-multiple",
            native_unit_of_measurement="VND",
            device_class=SensorDeviceClass.MONETARY,
            state_class=SensorStateClass.TOTAL,
            suggested_display_precision=0,
            value_fn=_period(part, "savings"),
            last_reset_fn=_period_reset(part),
            attrs_fn=_savings_attrs(part),
        )
        for part, suffix in _PERIODS
    ),
    LuxSensorDescription(
        # Số CHỐT của ngày hôm qua theo cloud (monthColumn) — dùng cho bản tin sáng.
        key="consumption_yesterday",
        name="Tiêu thụ hôm qua",
        icon="mdi:calendar-check",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=_period("yesterday", "consumption"),
        attrs_fn=lambda d: dict(_sub("periods")(d).get("yesterday") or {}),
    ),
)


def _quick_state(d: dict) -> str | None:
    """Trạng thái task quick; getStatusInfo lỗi ⇒ `None` (không phải `idle`)."""
    quick = _sub("quick")(d)
    if not quick:
        return None
    return (
        quick.get("charge_status")
        or quick.get("discharge_status")
        or ("charging" if quick.get("charging") else None)
        or ("discharging" if quick.get("discharging") else "idle")
    )


def _bits_on(d: dict) -> int | None:
    """Số bit đang bật; remoteRead lỗi ⇒ `None` (không phải 0 bit)."""
    bits = _sub("bits")(d)
    return sum(1 for v in bits.values() if v) if bits else None


SENSORS: tuple[LuxSensorDescription, ...] = (
    # ── Lưới (runtime) — nguồn dự phòng cho phát hiện mất điện lưới ──
    LuxSensorDescription(
        key="grid_voltage",
        name="Điện áp lưới",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _scaled(_sub("runtime")(d).get("vacr"), 10, 1),
    ),
    LuxSensorDescription(
        key="grid_frequency",
        name="Tần số lưới",
        icon="mdi:cosine-wave",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _scaled(_sub("runtime")(d).get("fac"), 100, 2),
    ),
    LuxSensorDescription(
        # Bitmask: 0x40 | 0x80 bật = đang chạy không lưới (xem binary_sensor.GRID_OFF_MASK).
        key="inverter_status",
        name="Mã trạng thái inverter",
        icon="mdi:state-machine",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _opt_int(_sub("runtime")(d).get("status")),
        attrs_fn=lambda d: {"status_text": _sub("runtime")(d).get("statusText", "")},
    ),
    LuxSensorDescription(
        # Giờ inverter ghi trong bản runtime cloud đang giữ — đo ĐỘ TƯƠI thật của số lưới
        # (dongle mất mạng thì cloud vẫn trả bản cũ, giờ này đứng yên).
        key="runtime_time",
        name="Dữ liệu inverter lúc",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _ts(_sub("runtime")(d).get("deviceTime")),
    ),
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
        # Tổng của NĂM hiện tại: tăng dần rồi về ~0 khi sang năm mới.
        # TOTAL (không last_reset) sẽ ghi cú tụt đó thành sản lượng ÂM trong
        # thống kê; TOTAL_INCREASING hiểu đó là reset chu kỳ.
        state_class=SensorStateClass.TOTAL_INCREASING,
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
        value_fn=_bits_on,
        attrs_fn=lambda d: {"bits": _sub("bits")(d)},
    ),
    LuxSensorDescription(
        key="quick_state",
        name="Trạng thái quick charge/discharge",
        icon="mdi:battery-sync-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_quick_state,
        attrs_fn=lambda d: _sub("quick")(d),
    ),
    LuxSensorDescription(
        key="plant_total_yield",
        name="Tổng sản lượng (plant)",
        icon="mdi:solar-power-variant",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: _kwh(_sub("plant")(d).get("total_yielding_text")),
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
        LuxCloudSensor(coordinator, serial, desc, parent_id)
        for desc in (*SENSORS, *PERIOD_SENSORS)
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
    def last_reset(self) -> datetime | None:
        if self.entity_description.last_reset_fn is None:
            return None
        return self.entity_description.last_reset_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data or {})
