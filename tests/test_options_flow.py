"""Test options flow — không chỉ schema, mà HÀNH VI: đổi tuỳ chọn thì entry reload.

Đây là chỗ dễ hỏng âm thầm: schema đúng nhưng listener không reload, hoặc reload
xong coordinator vẫn giữ interval cũ. Test cũ chỉ kiểm schema nên không bắt được.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType

from custom_components.luxcloud_ha.const import (
    CONF_ENABLE_FIRMWARE,
    CONF_ENABLE_SERIES,
    CONF_SCAN_INTERVAL,
)
from tests.conftest import setup_luxcloud

VALID_OPTIONS = {
    CONF_SCAN_INTERVAL: 600,
    CONF_ENABLE_SERIES: True,
    CONF_ENABLE_FIRMWARE: True,
}


async def _submit_options(hass, entry, options: dict):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(result["flow_id"], options)
    await hass.async_block_till_done()
    return result


async def test_options_flow_opens_a_form(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_submitting_options_creates_them(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)
    result = await _submit_options(hass, entry, dict(VALID_OPTIONS))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 600


async def test_changing_scan_interval_rebuilds_the_coordinator(hass, patched_api) -> None:
    """Coordinator phải thực sự chạy nhịp mới, không chỉ options đổi trên giấy."""
    entry = await setup_luxcloud(hass)
    original = entry.runtime_data
    assert original.update_interval == timedelta(seconds=300)

    await _submit_options(hass, entry, dict(VALID_OPTIONS))

    assert entry.runtime_data is not original, "entry phải được reload"
    assert entry.runtime_data.update_interval == timedelta(seconds=600)


async def test_disabling_firmware_takes_effect_after_reload(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)
    assert "firmware" in entry.runtime_data.data

    await _submit_options(
        hass,
        entry,
        {**VALID_OPTIONS, CONF_ENABLE_FIRMWARE: False},
    )

    assert "firmware" not in entry.runtime_data.data


async def test_disabling_series_takes_effect_after_reload(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)
    assert "day_curve" in entry.runtime_data.data

    await _submit_options(
        hass,
        entry,
        {**VALID_OPTIONS, CONF_ENABLE_SERIES: False},
    )

    assert "day_curve" not in entry.runtime_data.data
    assert "total_years" not in entry.runtime_data.data


async def test_entities_follow_the_new_scan_interval(hass, patched_api) -> None:
    """Entity phải trỏ vào coordinator MỚI, không phải cái đã bị bỏ."""
    from homeassistant.helpers import entity_registry as er

    entry = await setup_luxcloud(hass)
    await _submit_options(hass, entry, dict(VALID_OPTIONS))

    entity = hass.states.get("sensor.luxcloud_chu_ky_pin")
    assert entity is not None
    assert entity.state == "54", "dữ liệu phải còn sau reload"
    assert er.async_get(hass).async_get("sensor.luxcloud_chu_ky_pin") is not None


@pytest.mark.parametrize("bad_interval", [0, 30, 99999])
async def test_options_flow_rejects_a_bad_scan_interval(
    hass, patched_api, bad_interval: int
) -> None:
    entry = await setup_luxcloud(hass)
    before = dict(entry.options)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(vol.Invalid):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {**VALID_OPTIONS, CONF_SCAN_INTERVAL: bad_interval}
        )

    assert entry.options[CONF_SCAN_INTERVAL] == before[CONF_SCAN_INTERVAL]
