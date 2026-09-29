"""Diagnostics cho LuxCloud — che thông tin nhạy cảm TRƯỚC khi user tải file gửi đi.

File này là thứ user tải từ UI rồi dán lên GitHub issue, nên nó phải KHÔNG chứa:
  * mật khẩu tài khoản cloud
  * email tài khoản
  * serial inverter/dongle (dùng để định danh thiết bị)
  * id/tên plant (tên do user đặt, có thể là tên người/nhà)

Dùng `async_redact_data` của HA thay vì tự viết vòng lặp: nó che theo TÊN KHOÁ ở
mọi độ sâu, nên dữ liệu cloud lồng nhau (`dongle.sn`, `plant.plant_id`…) cũng được
che, và thêm khoá mới vào `TO_REDACT` là đủ.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ACCOUNT, CONF_PASSWORD, CONF_SERIAL

TO_REDACT = {
    # Khoá trong `entry.data`
    CONF_PASSWORD,      # "password"
    CONF_ACCOUNT,       # "account" — email
    CONF_SERIAL,        # "serial"
    # Khoá trong payload ĐÃ CHUẨN HOÁ của mình
    "sn",               # data.dongle.sn
    "serial_number",
    "plant_id",
    "plant_name",       # tên do user đặt
    # Tên field THẬT của cloud (camelCase) đi lọt nguyên vẹn trong runtime/energy.
    # Đo trên payload SỐNG: `runtime.serialNum` và `energy.serialNum` đều là serial
    # inverter. Fixture cũ không có 2 field này nên unit test không bắt được —
    # phải kéo file diagnostics thật từ HA mới thấy.
    "serialNum",
    "inverterSn",
    "datalogSn",
    "plantId",
    "userId",
}

DAY_CURVE_POINTS = 3    # chuỗi ngày có thể ~223 điểm → chỉ giữ vài điểm cho gọn


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Cấu hình (đã che) + dữ liệu lần poll gần nhất (đã che)."""
    coordinator = entry.runtime_data
    data = dict(coordinator.data or {})

    curve = data.get("day_curve") or {}
    if curve.get("points"):
        data["day_curve"] = {
            **curve,
            "points": curve["points"][:DAY_CURVE_POINTS],
            "_trimmed": True,
        }

    return async_redact_data(
        {
            "entry": {
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "coordinator": {
                "last_update_success": coordinator.last_update_success,
                "update_interval": str(coordinator.update_interval),
                "tick": getattr(coordinator, "_tick", None),
            },
            "data": data,
        },
        TO_REDACT,
    )
