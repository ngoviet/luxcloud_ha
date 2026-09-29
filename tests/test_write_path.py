"""Test đường GHI của Phase 2 — switch, button và service `set_bit`.

Mọi test ở đây bấm qua đúng service của HA (`switch.turn_on`, `button.press`,
`luxcloud_ha.set_bit`) rồi kiểm hai thứ: lệnh nào được gửi lên cloud, và trạng
thái entity sau đó. Không test nào đọc source code.
"""
from __future__ import annotations

import asyncio

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from custom_components.luxcloud_ha import SERVICE_SET_BIT
from custom_components.luxcloud_ha.const import DOMAIN, QUICK_CHARGE, QUICK_DISCHARGE
from tests.conftest import setup_luxcloud

SWITCH_TO_BIT = {
    "switch.luxcloud_grid_peak_shaving": "FUNC_GRID_PEAK_SHAVING",
    "switch.luxcloud_gen_peak_shaving": "FUNC_GEN_PEAK_SHAVING",
    "switch.luxcloud_active_power_limit_mode": "FUNC_ACTIVE_POWER_LIMIT_MODE",
}

BUTTON_TO_CALL = {
    "button.luxcloud_quick_charge_start": (QUICK_CHARGE, "start"),
    "button.luxcloud_quick_charge_stop": (QUICK_CHARGE, "stop"),
    "button.luxcloud_quick_discharge_start": (QUICK_DISCHARGE, "start"),
    "button.luxcloud_quick_discharge_stop": (QUICK_DISCHARGE, "stop"),
}

ALL_SWITCHES = list(SWITCH_TO_BIT)
ALL_BUTTONS = list(BUTTON_TO_CALL)


async def _call(hass, domain: str, service: str, data: dict) -> None:
    await hass.services.async_call(domain, service, data, blocking=True)
    await hass.async_block_till_done()


def _set_quick_state(api, *, charging: bool = False, discharging: bool = False) -> None:
    api.data["quick"] = {
        **api.data["quick"],
        "charging": charging,
        "discharging": discharging,
        "charge_status": "WAIT_CHARGE" if charging else "",
        "discharge_status": "WAIT_DISCHARGE" if discharging else "",
    }


async def _refresh(hass) -> None:
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


# ── Switch: bit cấu hình HR[179] ───────────────────────────────


@pytest.mark.parametrize("entity_id", ALL_SWITCHES)
async def test_turn_on_writes_that_switch_bit(
    hass, patched_api, no_write_settle, entity_id: str
) -> None:
    await setup_luxcloud(hass)

    await _call(hass, "switch", "turn_on", {"entity_id": entity_id})

    api = patched_api.instances[-1]
    assert api.bit_writes == [(SWITCH_TO_BIT[entity_id], True)]
    assert hass.states.get(entity_id).state == "on"


@pytest.mark.parametrize("entity_id", ALL_SWITCHES)
async def test_turn_off_writes_false(
    hass, patched_api, no_write_settle, entity_id: str
) -> None:
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    api.data["bits"][SWITCH_TO_BIT[entity_id]] = True
    await _refresh(hass)
    assert hass.states.get(entity_id).state == "on"

    await _call(hass, "switch", "turn_off", {"entity_id": entity_id})

    assert api.bit_writes == [(SWITCH_TO_BIT[entity_id], False)]
    assert hass.states.get(entity_id).state == "off"


async def test_turning_on_one_switch_does_not_touch_the_others(
    hass, patched_api, no_write_settle
) -> None:
    await setup_luxcloud(hass)

    await _call(hass, "switch", "turn_on", {"entity_id": "switch.luxcloud_gen_peak_shaving"})

    api = patched_api.instances[-1]
    assert api.bit_writes == [("FUNC_GEN_PEAK_SHAVING", True)]
    assert hass.states.get("switch.luxcloud_grid_peak_shaving").state == "off"
    assert hass.states.get("switch.luxcloud_active_power_limit_mode").state == "off"


async def test_rejected_write_raises_and_keeps_the_switch_off(
    hass, patched_api, no_write_settle
) -> None:
    """Cloud từ chối ⇒ service phải báo lỗi, KHÔNG được hiện trạng thái đã bật."""
    await setup_luxcloud(hass)
    patched_api.bit_write_result = False

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, "switch", "turn_on", {"entity_id": "switch.luxcloud_grid_peak_shaving"})

    assert "FUNC_GRID_PEAK_SHAVING" in str(err.value)
    assert hass.states.get("switch.luxcloud_grid_peak_shaving").state == "off"


async def test_switch_is_unavailable_when_cloud_returns_no_bits(
    hass, patched_api
) -> None:
    """Không có dữ liệu bit thì không được đoán trạng thái để người dùng bấm."""
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    api.data["bits"] = {}
    await _refresh(hass)

    for entity_id in ALL_SWITCHES:
        assert hass.states.get(entity_id).state == "unavailable", entity_id


async def test_switch_unavailable_when_its_own_bit_key_is_missing(
    hass, patched_api
) -> None:
    """Thiếu đúng key bit của switch ⇒ switch đó unavailable, key còn lại vẫn bình thường."""
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    del api.data["bits"]["FUNC_GRID_PEAK_SHAVING"]
    await _refresh(hass)

    assert hass.states.get("switch.luxcloud_grid_peak_shaving").state == "unavailable"
    assert hass.states.get("switch.luxcloud_gen_peak_shaving").state != "unavailable"
    assert hass.states.get("switch.luxcloud_active_power_limit_mode").state != "unavailable"


# ── Button: quick charge / discharge ──────────────────────────


@pytest.mark.parametrize("entity_id", ALL_BUTTONS)
async def test_button_press_calls_the_matching_endpoint(
    hass, patched_api, no_write_settle, entity_id: str
) -> None:
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    action, op = BUTTON_TO_CALL[entity_id]
    # Nút chỉ bấm được khi nó available: `start` cần task đang rảnh, `stop` cần đang chạy.
    running = op == "stop"
    _set_quick_state(
        api,
        charging=running and action == QUICK_CHARGE,
        discharging=running and action == QUICK_DISCHARGE,
    )
    await _refresh(hass)
    assert hass.states.get(entity_id).state != "unavailable", entity_id

    await _call(hass, "button", "press", {"entity_id": entity_id})

    assert api.quick_writes == [BUTTON_TO_CALL[entity_id]]


async def test_rejected_quick_press_raises(hass, patched_api, no_write_settle) -> None:
    await setup_luxcloud(hass)
    patched_api.quick_write_result = False

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, "button", "press", {"entity_id": "button.luxcloud_quick_charge_start"})

    assert "quickCharge" in str(err.value)


async def test_start_button_is_available_only_while_idle(hass, patched_api) -> None:
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]

    assert hass.states.get("button.luxcloud_quick_charge_start").state != "unavailable"

    _set_quick_state(api, charging=True)
    await _refresh(hass)

    assert hass.states.get("button.luxcloud_quick_charge_start").state == "unavailable"
    assert hass.states.get("button.luxcloud_quick_charge_stop").state != "unavailable"


async def test_all_buttons_available_when_quick_status_is_missing(hass, patched_api) -> None:
    """Không có quick status ⇒ không được đoán 'idle' mà phải để cả 4 nút bấm được."""
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    del api.data["quick"]
    await _refresh(hass)

    for entity_id in ALL_BUTTONS:
        assert hass.states.get(entity_id).state != "unavailable", entity_id


async def test_charge_and_discharge_buttons_follow_their_own_task(
    hass, patched_api
) -> None:
    """Đang charge ⇒ start-charge ẩn, stop-charge hiện; discharge giữ luật riêng."""
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    _set_quick_state(api, charging=True)
    await _refresh(hass)

    assert hass.states.get("button.luxcloud_quick_charge_start").state == "unavailable"
    assert hass.states.get("button.luxcloud_quick_charge_stop").state != "unavailable"
    assert hass.states.get("button.luxcloud_quick_discharge_start").state != "unavailable"
    assert hass.states.get("button.luxcloud_quick_discharge_stop").state == "unavailable"


async def test_idle_buttons_show_start_available_and_stop_unavailable(
    hass, patched_api
) -> None:
    """Mọi task rảnh ⇒ start hiện, stop ẩn."""
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    _set_quick_state(api)
    await _refresh(hass)

    assert hass.states.get("button.luxcloud_quick_charge_start").state != "unavailable"
    assert hass.states.get("button.luxcloud_quick_charge_stop").state == "unavailable"
    assert hass.states.get("button.luxcloud_quick_discharge_start").state != "unavailable"
    assert hass.states.get("button.luxcloud_quick_discharge_stop").state == "unavailable"


# ── Service set_bit ───────────────────────────────────────────


async def test_set_bit_service_is_registered(hass, patched_api) -> None:
    await setup_luxcloud(hass)
    assert hass.services.has_service(DOMAIN, SERVICE_SET_BIT)


async def test_set_bit_service_writes_an_exposed_and_a_nonexposed_bit(
    hass, patched_api, no_write_settle
) -> None:
    """Service dùng được cho cả bit KHÔNG có switch (vd FUNC_RSD_DISABLE)."""
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]

    await _call(hass, DOMAIN, SERVICE_SET_BIT, {"function": "FUNC_RSD_DISABLE", "enable": True})
    await _call(
        hass, DOMAIN, SERVICE_SET_BIT, {"function": "FUNC_GRID_PEAK_SHAVING", "enable": True}
    )

    assert api.bit_writes == [("FUNC_RSD_DISABLE", True), ("FUNC_GRID_PEAK_SHAVING", True)]

    await _refresh(hass)
    assert hass.states.get("switch.luxcloud_grid_peak_shaving").state == "on"


async def test_set_bit_service_coerces_string_false_to_false(
    hass, patched_api, no_write_settle
) -> None:
    """Chuỗi 'false' phải ghi False, KHÔNG được coi là truthy rồi ghi True."""
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]

    await _call(
        hass, DOMAIN, SERVICE_SET_BIT, {"function": "FUNC_RSD_DISABLE", "enable": "false"}
    )

    assert api.bit_writes == [("FUNC_RSD_DISABLE", False)]


async def test_set_bit_service_asks_the_coordinator_to_refresh(
    hass, patched_api, no_write_settle
) -> None:
    """Ghi xong phải poll lại, nếu không entity sẽ hiển thị giá trị cũ."""
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    before = len(api.fetch_calls)

    await _call(hass, DOMAIN, SERVICE_SET_BIT, {"function": "FUNC_RSD_DISABLE", "enable": True})

    assert len(api.fetch_calls) > before


async def test_set_bit_service_waits_for_write_settle_before_refresh(
    hass, patched_api, monkeypatch
) -> None:
    """Ghi xong phải đợi cloud→dongle (CONFIG_WRITE_SETTLE) rồi mới poll lại."""
    await setup_luxcloud(hass)
    real_sleep = asyncio.sleep
    delays: list[float] = []

    async def recording_sleep(delay: float, *args, **kwargs) -> None:
        delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr("custom_components.luxcloud_ha.asyncio.sleep", recording_sleep)
    monkeypatch.setattr("custom_components.luxcloud_ha.CONFIG_WRITE_SETTLE", 1.5)

    await _call(hass, DOMAIN, SERVICE_SET_BIT, {"function": "FUNC_RSD_DISABLE", "enable": True})

    assert [d for d in delays if d] == [1.5]


async def test_set_bit_service_skips_wait_when_settle_is_zero(
    hass, patched_api, monkeypatch
) -> None:
    """CONFIG_WRITE_SETTLE = 0 ⇒ không đợi, poll lại ngay."""
    await setup_luxcloud(hass)
    real_sleep = asyncio.sleep
    delays: list[float] = []

    async def recording_sleep(delay: float, *args, **kwargs) -> None:
        delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr("custom_components.luxcloud_ha.asyncio.sleep", recording_sleep)
    monkeypatch.setattr("custom_components.luxcloud_ha.CONFIG_WRITE_SETTLE", 0)

    await _call(hass, DOMAIN, SERVICE_SET_BIT, {"function": "FUNC_RSD_DISABLE", "enable": True})

    assert [d for d in delays if d] == []


async def test_set_bit_service_reports_a_rejected_write(
    hass, patched_api, no_write_settle
) -> None:
    await setup_luxcloud(hass)
    patched_api.bit_write_result = False

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, DOMAIN, SERVICE_SET_BIT, {"function": "FUNC_RSD_DISABLE", "enable": True})

    assert "FUNC_RSD_DISABLE" in str(err.value)


@pytest.mark.parametrize("bad", ["GRID_PEAK_SHAVING", "func_grid", "", "FUNC_lower", "FUNC_A-B"])
async def test_set_bit_service_rejects_a_bad_function_name(
    hass, patched_api, no_write_settle, bad: str
) -> None:
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]

    with pytest.raises(vol.Invalid):
        await _call(hass, DOMAIN, SERVICE_SET_BIT, {"function": bad, "enable": True})

    assert api.bit_writes == [], "tên bit sai không được gửi lên cloud"


async def test_set_bit_service_refuses_to_guess_between_two_inverters(
    hass, patched_api, no_write_settle
) -> None:
    """Ghi nhầm inverter là hỏng thật ⇒ không target + nhiều inverter phải báo lỗi."""
    await setup_luxcloud(hass, serial="61204F0266")
    await setup_luxcloud(hass, serial="61204F0267")
    assert len(patched_api.instances) == 2
    for api in patched_api.instances:
        api.bit_writes.clear()

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, DOMAIN, SERVICE_SET_BIT, {"function": "FUNC_RSD_DISABLE", "enable": True})

    assert "nhiều inverter" in str(err.value).lower() or "thiết bị" in str(err.value).lower()
    assert all(api.bit_writes == [] for api in patched_api.instances)


async def test_set_bit_service_writes_only_the_targeted_inverter(
    hass, patched_api, no_write_settle
) -> None:
    """Có target device ⇒ chỉ inverter đó bị ghi."""
    from homeassistant.helpers import entity_registry as er

    await setup_luxcloud(hass, serial="61204F0266")
    await setup_luxcloud(hass, serial="61204F0267")
    for api in patched_api.instances:
        api.bit_writes.clear()

    registry = er.async_get(hass)
    candidates = [
        e
        for e in registry.entities.values()
        if e.entity_id.startswith("switch.luxcloud_active_power_limit_mode")
    ]
    assert len(candidates) == 2, [e.entity_id for e in candidates]
    target = sorted(candidates, key=lambda e: e.entity_id)[-1]

    await _call(
        hass,
        DOMAIN,
        SERVICE_SET_BIT,
        {"function": "FUNC_RSD_DISABLE", "enable": True, "device_id": target.device_id},
    )

    written = [api for api in patched_api.instances if api.bit_writes]
    assert len(written) == 1, [api.bit_writes for api in patched_api.instances]
    assert written[0].bit_writes == [("FUNC_RSD_DISABLE", True)]


async def test_set_bit_service_rejects_a_target_from_another_integration(
    hass, patched_api, no_write_settle
) -> None:
    """Target thuộc integration khác ⇒ phải báo lỗi, KHÔNG ghi nhầm inverter duy nhất."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.helpers import device_registry as dr

    await setup_luxcloud(hass)
    api = patched_api.instances[-1]

    other_entry = MockConfigEntry(
        domain="mqtt",
        title="MQTT",
        data={},
        entry_id="mqtt_entry_1",
    )
    other_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={("mqtt", "device-1")},
        name="MQTT device",
    )
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await _call(
            hass,
            DOMAIN,
            SERVICE_SET_BIT,
            {"function": "FUNC_RSD_DISABLE", "enable": True, "device_id": device.id},
        )

    assert api.bit_writes == []


async def test_set_bit_service_rejects_a_target_whose_entry_is_unloaded(
    hass, patched_api, no_write_settle
) -> None:
    """Target trỏ vào entry CHƯA/không còn loaded ⇒ báo lỗi HA, KHÔNG AttributeError."""
    from homeassistant.helpers import device_registry as dr

    entry = await setup_luxcloud(hass)
    api = patched_api.instances[-1]
    device = next(
        iter(dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id))
    )

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED

    with pytest.raises(HomeAssistantError) as err:
        await _call(
            hass,
            DOMAIN,
            SERVICE_SET_BIT,
            {"function": "FUNC_RSD_DISABLE", "enable": True, "device_id": device.id},
        )

    assert not isinstance(err.value, AttributeError)
    assert api.bit_writes == []

