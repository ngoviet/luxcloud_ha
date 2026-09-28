"""Device info cho LuxCloud: 1 device inverter + 1 device dongle (via_device)."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

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


def dongle_device_info(coordinator, serial: str) -> DeviceInfo:
    """Device dongle: nối vào device inverter qua via_device."""
    dongle = _sub(coordinator, "dongle")
    sn = dongle.get("sn") or "unknown"
    return DeviceInfo(
        identifiers={(DOMAIN, f"dongle-{sn}")},
        name=DEVICE_NAME_DONGLE,
        manufacturer=MANUFACTURER,
        model=dongle.get("type_text") or dongle.get("type") or "Datalog",
        sw_version=dongle.get("firmware") or None,
        serial_number=sn,
        via_device=(DOMAIN, f"inverter-{serial}"),
    )
