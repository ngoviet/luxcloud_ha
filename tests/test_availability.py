"""Test hành vi khi cloud lỗi — entity phải `unavailable`, không giữ số cũ.

Giữ số cũ là kiểu hỏng nguy hiểm nhất: user nhìn thấy 54 chu kỳ pin / 3381 mV và
tưởng dữ liệu còn sống, trong khi cloud đã chết từ lâu.
"""
from __future__ import annotations

import pytest

from custom_components.luxcloud_ha.api import LuxCloudApiError, LuxCloudAuthError
from custom_components.luxcloud_ha.const import DOMAIN
from tests.conftest import setup_luxcloud

# Đủ 4 platform — mỗi platform dựa vào `CoordinatorEntity.available`.
ONE_PER_PLATFORM = {
    "sensor.luxcloud_chu_ky_pin": "54",
    "binary_sensor.luxcloud_co_firmware_moi": "on",
    "switch.luxcloud_grid_peak_shaving": "off",
    "button.luxcloud_quick_charge_start": None,  # nút không có state cố định
}


async def _refresh(hass):
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    return entry


@pytest.mark.no_fail_on_log_exception
async def test_entities_go_unavailable_when_the_cloud_fails(hass, patched_api) -> None:
    await setup_luxcloud(hass)
    assert hass.states.get("sensor.luxcloud_chu_ky_pin").state == "54"

    patched_api.fetch_error = LuxCloudApiError("mạng lỗi")
    await _refresh(hass)

    for entity_id in ONE_PER_PLATFORM:
        assert hass.states.get(entity_id).state == "unavailable", entity_id


@pytest.mark.no_fail_on_log_exception
async def test_entities_recover_when_the_cloud_comes_back(hass, patched_api) -> None:
    await setup_luxcloud(hass)

    patched_api.fetch_error = LuxCloudApiError("mạng lỗi")
    await _refresh(hass)
    assert hass.states.get("sensor.luxcloud_chu_ky_pin").state == "unavailable"

    patched_api.fetch_error = None
    await _refresh(hass)

    for entity_id, expected in ONE_PER_PLATFORM.items():
        if expected is None:
            continue
        assert hass.states.get(entity_id).state == expected, entity_id


@pytest.mark.no_fail_on_log_exception
async def test_last_good_data_is_kept_for_the_next_successful_poll(hass, patched_api) -> None:
    """Lỗi tạm thời không được xoá dữ liệu — nếu không, lần poll sau sẽ trắng."""
    entry = await setup_luxcloud(hass)

    patched_api.fetch_error = LuxCloudApiError("mạng lỗi")
    await _refresh(hass)

    assert entry.runtime_data.last_update_success is False
    assert entry.runtime_data.data["battery"]["cycles"] == 54


@pytest.mark.no_fail_on_log_exception
async def test_auth_failure_starts_a_reauth_flow(hass, patched_api) -> None:
    """Sai mật khẩu giữa chừng phải đưa user tới form đăng nhập lại, không chỉ log lỗi."""
    await setup_luxcloud(hass)

    patched_api.fetch_error = LuxCloudAuthError("sai mật khẩu")
    await _refresh(hass)

    flows = hass.config_entries.flow.async_progress()
    reauth = [
        f
        for f in flows
        if f["handler"] == DOMAIN and f["context"].get("source") == "reauth"
    ]
    assert reauth, f"không thấy reauth flow: {flows}"


@pytest.mark.no_fail_on_log_exception
async def test_transient_failure_then_auth_failure_does_not_crash(hass, patched_api) -> None:
    """Đổi kiểu lỗi liên tiếp không được làm nổ setup/entity."""
    await setup_luxcloud(hass)

    patched_api.fetch_error = LuxCloudApiError("mạng lỗi")
    await _refresh(hass)
    patched_api.fetch_error = LuxCloudAuthError("sai mật khẩu")
    await _refresh(hass)

    assert hass.states.get("sensor.luxcloud_chu_ky_pin").state == "unavailable"
