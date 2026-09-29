"""Test diagnostics — file user tải từ UI rồi dán lên GitHub issue.

Đây là test về RÒ RỈ DỮ LIỆU, nên cách kiểm mạnh nhất là: serialize cả file ra
JSON rồi quét xem giá trị bí mật có xuất hiện ở BẤT KỲ đâu không — chứ không chỉ
kiểm vài khoá ở tầng trên.
"""
from __future__ import annotations

import json

import pytest
from homeassistant.components.diagnostics import REDACTED

from custom_components.luxcloud_ha.diagnostics import (
    DAY_CURVE_POINTS,
    async_get_config_entry_diagnostics,
)
from tests.conftest import TEST_ACCOUNT, TEST_PASSWORD, setup_luxcloud

INVERTER_SERIAL = "61204F0266"
DONGLE_SN = "DU61242846"        # trong payload đã chuẩn hoá: data.dongle.sn
PLANT_NAME = "Nhà anh Ngô"      # tên do user đặt — PII
PLANT_ID = 123456


async def _diagnostics(hass, entry) -> dict:
    return await async_get_config_entry_diagnostics(hass, entry)


def _as_json(diag: dict) -> str:
    return json.dumps(diag, ensure_ascii=False)


# ── Không được lọt secret ──────────────────────────────────────


async def test_no_secret_value_appears_anywhere_in_the_file(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)
    blob = _as_json(await _diagnostics(hass, entry))

    for label, secret in (
        ("mật khẩu", TEST_PASSWORD),
        ("email tài khoản", TEST_ACCOUNT),
        ("serial inverter", INVERTER_SERIAL),
        ("serial dongle", DONGLE_SN),
        ("tên plant", PLANT_NAME),
        ("id plant", str(PLANT_ID)),
    ):
        assert secret not in blob, f"diagnostics làm lọt {label}: {secret!r}"


async def test_credentials_are_replaced_by_the_ha_marker(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)
    diag = await _diagnostics(hass, entry)

    assert diag["entry"]["data"]["password"] == REDACTED
    assert diag["entry"]["data"]["account"] == REDACTED
    assert diag["entry"]["data"]["serial"] == REDACTED


async def test_nested_cloud_identifiers_are_redacted_too(hass, patched_api) -> None:
    """`async_redact_data` che theo tên khoá ở mọi độ sâu — kiểm điều đó thật sự xảy ra."""
    entry = await setup_luxcloud(hass)
    diag = await _diagnostics(hass, entry)

    assert diag["data"]["dongle"]["sn"] == REDACTED
    assert diag["data"]["plant"]["plant_id"] == REDACTED
    assert diag["data"]["plant"]["plant_name"] == REDACTED


async def test_camelcase_serialnum_fields_are_redacted(hass, patched_api) -> None:
    """`serialNum` là tên field THẬT của cloud — bản đầu của file này đã để lọt.

    Fixture phải giữ đúng 2 field đó, nếu không test lại mù như lần trước.
    """
    entry = await setup_luxcloud(hass)
    diag = await _diagnostics(hass, entry)

    assert diag["data"]["runtime"]["serialNum"] == REDACTED
    assert diag["data"]["energy"]["serialNum"] == REDACTED


# ── Vẫn phải dùng được để debug ────────────────────────────────


async def test_file_still_contains_what_we_need_to_debug(hass, patched_api) -> None:
    """Che quá tay thì file vô dụng — dữ liệu chẩn đoán phải còn."""
    entry = await setup_luxcloud(hass)
    diag = await _diagnostics(hass, entry)

    assert diag["data"]["battery"]["cycles"] == 54
    assert diag["data"]["battery"]["cell_delta_mv"] == 4
    assert diag["data"]["health"]["fw_code"] == "CHAA-000303"
    assert diag["data"]["bits"]["FUNC_GRID_PEAK_SHAVING"] is False
    assert diag["coordinator"]["last_update_success"] is True
    assert diag["coordinator"]["update_interval"] == "0:05:00"


async def test_options_are_kept_unredacted(hass, patched_api) -> None:
    """`scan_interval`/cờ bật-tắt không phải bí mật, phải đọc được."""
    entry = await setup_luxcloud(hass)
    options = (await _diagnostics(hass, entry))["entry"]["options"]

    assert options["scan_interval"] == 300
    assert options["enable_series"] is True
    assert options["enable_firmware"] is True


# ── Cắt bớt chuỗi ngày ─────────────────────────────────────────


async def test_day_curve_is_trimmed(hass, patched_api) -> None:
    """Chuỗi ngày có thể ~223 điểm — file diagnostics phải gọn."""
    entry = await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    api.data["day_curve"] = {
        "date": "2026-09-28",
        "count": 10,
        "points": [{"time": f"{i:02d}:00", "solarPv": i} for i in range(10)],
    }
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    curve = (await _diagnostics(hass, entry))["data"]["day_curve"]

    assert curve["_trimmed"] is True
    assert len(curve["points"]) == DAY_CURVE_POINTS
    assert curve["count"] == 10, "số điểm gốc phải còn để biết đã cắt"


async def test_day_curve_without_points_is_left_alone(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    api.data["day_curve"] = {"date": "2026-09-28", "count": 0, "points": []}
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    curve = (await _diagnostics(hass, entry))["data"]["day_curve"]
    assert curve["points"] == []
    assert "_trimmed" not in curve


# ── Hợp đồng với HA ────────────────────────────────────────────


async def test_output_is_json_serialisable(hass, patched_api) -> None:
    """HA serialize kết quả này — có kiểu lạ là hỏng lúc tải file."""
    entry = await setup_luxcloud(hass)
    diag = await _diagnostics(hass, entry)

    text = json.dumps(diag)
    assert json.loads(text)["entry"]["data"]["password"] == REDACTED


# ── trạng thái coordinator ─────────────────────────────────────


async def test_coordinator_state_is_reported_when_healthy(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)
    coord = (await _diagnostics(hass, entry))["coordinator"]

    assert coord["last_update_success"] is True
    assert coord["failed_updates"] == 0
    assert coord["last_exception"] is None
    assert coord["last_update_success_time"] is not None
    assert coord["update_interval"] == "0:05:00"
    assert coord["tick"] == 1


@pytest.mark.no_fail_on_log_exception
async def test_coordinator_state_shows_a_flaky_cloud(hass, patched_api) -> None:
    """Thứ giúp phân biệt 'cloud chập chờn' với 'sai cấu hình' mà không cần mở log."""
    from custom_components.luxcloud_ha.api import LuxCloudApiError

    entry = await setup_luxcloud(hass)
    patched_api.fetch_error = LuxCloudApiError("mạng lỗi")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    coord = (await _diagnostics(hass, entry))["coordinator"]
    assert coord["last_update_success"] is False
    assert coord["failed_updates"] == 1
    assert "UpdateFailed" in coord["last_exception"]


@pytest.mark.no_fail_on_log_exception
async def test_recovery_resets_the_failure_counter(hass, patched_api) -> None:
    from custom_components.luxcloud_ha.api import LuxCloudApiError

    entry = await setup_luxcloud(hass)
    patched_api.fetch_error = LuxCloudApiError("mạng lỗi")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    patched_api.fetch_error = None
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    coord = (await _diagnostics(hass, entry))["coordinator"]
    assert coord["last_update_success"] is True
    assert coord["failed_updates"] == 0

