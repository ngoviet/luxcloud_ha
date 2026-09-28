"""Device info cho LuxCloud: 1 device inverter + 1 device dongle (nối bằng via_device_id).

⚠️ HA 2026.x **deprecated** key `via_device` (tuple identifier) — bản đồ deprecation trong
`homeassistant/helpers/device_registry.py`:
    "via_device": ("2027.8.0", "via_device_id")
Log thật của HA 2026.9.3 khi còn dùng `via_device`:
    Detected that custom integration 'luxcloud_ha' calls `device_registry.async_get_or_create`
    with a deprecated `via_device` parameter; use `via_device_id` instead ...
    This will stop working in Home Assistant 2027.8.0
⇒ Ở đây dùng `via_device_id` (id thật trong device registry). Vì id đó chỉ có sau khi device
inverter được đăng ký, `__init__.py` đăng ký device inverter TRƯỚC khi load platform, rồi
platform tra id bằng `parent_device_id()` bên dưới.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    DeviceInfo,
    async_get_device_id_by_identifier,
)

from .const import DEVICE_NAME, DEVICE_NAME_DONGLE, DOMAIN, MANUFACTURER


def _sub(coordinator, key: str) -> dict:
    return (coordinator.data or {}).get(key) or {}


def device_info(coordinator, serial: str) -> DeviceInfo:
    """Device chính: inverter (model/fw/hw/serial lấy từ cloud)."""
    plant = _sub(coordinator, "plant")
    health = _sub(coordinator, "health")
    rating = health.get("power_rating") or ""
    standard = plant.get("standard") or ""
    model = " ".join(x for x in (str(rating), f"({standard})" if standard else "") if x)
    hw = plant.get("hardware_version", -1)
    return DeviceInfo(
        identifiers={(DOMAIN, f"inverter-{serial}")},
        name=DEVICE_NAME,
        manufacturer=MANUFACTURER,
        model=model or "Inverter",
        sw_version=health.get("fw_code") or None,
        hw_version=f"HW{hw}" if isinstance(hw, int) and hw >= 0 else None,
        serial_number=serial,
        configuration_url="https://www.luxpowertek.com/",
    )


def dongle_device_info(
    coordinator, serial: str, via_device_id: str | None = None
) -> DeviceInfo:
    """Device dongle, nối vào device inverter qua `via_device_id` (API mới của HA)."""
    dongle = _sub(coordinator, "dongle")
    sn = dongle.get("sn") or "unknown"
    info = DeviceInfo(
        identifiers={(DOMAIN, f"dongle-{sn}")},
        name=DEVICE_NAME_DONGLE,
        manufacturer=MANUFACTURER,
        model=dongle.get("type_text") or dongle.get("type") or "Datalog",
        sw_version=dongle.get("firmware") or None,
        serial_number=sn,
    )
    if via_device_id:
        info["via_device_id"] = via_device_id
    return info


def parent_device_id(hass: HomeAssistant, serial: str, entry_id: str) -> str | None:
    """Id trong device registry của device inverter (None nếu chưa đăng ký).

    Dùng `async_get_device_id_by_identifier` — helper của HA cho ĐÚNG việc này
    ("Convenience wrapper for linking a device to its via device through via_device_id").
    KHÔNG dùng `DeviceRegistry.async_get_device(identifiers=...)`: từ HA 2026.x nó deprecated
    ("device identifiers and connections are no longer unique across config entries") và sẽ
    ngừng hoạt động ở 2027.8 — đo thật bằng log HA 2026.9.3.
    """
    try:
        return async_get_device_id_by_identifier(
            hass, (DOMAIN, f"inverter-{serial}"), config_entry_id=entry_id
        )
    except ValueError:
        return None
