"""Diagnostics cho LuxCloud (che mật khẩu)."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Trả về cấu hình (đã che) + dữ liệu lần poll gần nhất."""
    coordinator = entry.runtime_data
    data = dict(coordinator.data or {})
    # chuỗi ngày có thể dài → chỉ giữ vài điểm cho gọn
    curve = data.get("day_curve") or {}
    if curve.get("points"):
        data["day_curve"] = {**curve, "points": curve["points"][:3], "_trimmed": True}
    return {
        "entry": {
            "data": {k: ("***" if k == CONF_PASSWORD else v) for k, v in entry.data.items()},
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "tick": getattr(coordinator, "_tick", None),
        },
        "data": data,
    }
