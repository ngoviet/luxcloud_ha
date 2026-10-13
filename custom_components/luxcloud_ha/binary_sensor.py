"""Binary sensor platform — cờ trạng thái của LuxCloud (Phase 1)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
    is_on_fn: Callable[[dict], bool | None]  # None = không biết → state `unknown`
    dongle: bool = False
    attrs_fn: Callable[[dict], dict] | None = None


def _sub(key: str) -> Callable[[dict], dict]:
    return lambda d: d.get(key) or {}


# Bit "đang chạy không lưới" trong trường `runtime.status` (bitmask):
#   0x40 = pin đang gánh EPS (mất lưới)
#   0x80 = PV không đủ cho EPS (mất lưới)
#   0xC0 = PV + pin gánh EPS (mất lưới)
#   0x88 = PV gánh EPS, phần dư sạc pin (mất lưới)
# ⇒ hai bit cao (0xC0) luôn bật khi inverter chạy không lưới. Bảng bit:
# https://github.com/celsworth/lxp-bridge/wiki/Inputs#status
GRID_OFF_MASK = 0xC0


def _off_grid(d: dict) -> bool | None:
    """True khi inverter đang chạy không lưới (EPS / off-grid).

    ⚠️ Sửa 2026-09-30: bản cũ đọc `runtime.isOffGrid` — **key này KHÔNG tồn tại**
    trong response `web/maintain/remoteRead/read` của SNA PRO (đối chiếu payload
    thật lúc 07:11 ngày 30/09/2026, khi inverter ĐANG chạy EPS: không có key
    `isOffGrid`, nhưng `status = 192` = 0xC0). Hệ quả bản cũ: cờ luôn `off`,
    kể cả khi mất lưới thật ⇒ không dùng được để cảnh báo mất điện.
    """
    rt = _sub("runtime")(d)
    status = rt.get("status")
    if status is not None:
        try:
            return (int(status) & GRID_OFF_MASK) != 0
        except (TypeError, ValueError):
            pass
    # Không có số đo lưới (runtime lỗi trong khi plant vẫn trả) ⇒ KHÔNG BIẾT,
    # không phải "mất lưới". Bản cũ coi thiếu = 0 V ⇒ báo mất điện giả.
    if rt.get("vacr") is None and rt.get("fac") is None:
        return None
    # Dự phòng khi cloud không trả `status`: không có AC ở ngõ vào lưới.
    try:
        vacr = float(rt.get("vacr") or 0)
        fac = float(rt.get("fac") or 0)
    except (TypeError, ValueError):
        return False
    return not (vacr >= 100 or fac >= 45)


def _off_grid_attrs(d: dict) -> dict:
    rt = _sub("runtime")(d)
    return {
        "status": rt.get("status"),
        "grid_voltage_v": rt.get("vacr"),
        "grid_frequency_hz": rt.get("fac"),
        "eps_power_w": rt.get("peps"),
        "note": (
            "isOffGrid không có trong payload runtime của SNA PRO; "
            "dùng status & 0xC0 (bit 0x40/0x80) — xem lxp-bridge wiki §Status."
        ),
    }


def _firmware_available(d: dict) -> bool:
    """Catalog mới hơn fwVersion của inverter.

    `get_plant` ghi `fw_version = -1` khi cloud không trả `fwVersion` — đó là
    KHÔNG BIẾT, không phải version -1 (bản cũ: 8 > -1 ⇒ báo có firmware mới giả).
    """
    dev = _sub("plant")(d).get("fw_version")
    latest = _sub("firmware")(d).get("latest_version")
    if dev is None or latest is None or int(dev) < 0:
        return False
    return int(latest) > int(dev)


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
        # PROBLEM, không phải CONNECTIVITY: với CONNECTIVITY, `on` nghĩa là ĐANG
        # kết nối, trong khi is_on ở đây = MẤT kết nối → UI hiện ngược ("Đã kết
        # nối" khi dongle mất). PROBLEM giữ nguyên state on/off (automation cũ
        # không vỡ) và hiển thị đúng nghĩa "có sự cố".
        device_class=BinarySensorDeviceClass.PROBLEM,
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
        is_on_fn=_firmware_available,
        attrs_fn=_firmware_attrs,
    ),
    LuxBinaryDescription(
        key="off_grid",
        # Tên đổi 2026-09-30 (bỏ "(isOffGrid)" vì key đó không tồn tại trong API).
        # ⚠️ `unique_id` giữ nguyên (`{serial}_off_grid`) nên entity_id trong
        # registry vẫn là `binary_sensor.luxcloud_dang_chay_khong_luoi_isoffgrid`
        # cho tới khi đổi tay trong Settings → Entities.
        name="Đang chạy không lưới (EPS)",
        icon="mdi:transmission-tower-off",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=_off_grid,
        attrs_fn=_off_grid_attrs,
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
    def is_on(self) -> bool | None:
        try:
            value = self.entity_description.is_on_fn(self.coordinator.data or {})
        except (TypeError, ValueError):
            return False
        return None if value is None else bool(value)

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data or {})
