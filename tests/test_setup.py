"""Test setup đầy đủ: entry được load, 36 entity, liên kết device dongle→inverter.

Đây là test bắt regression cho hai quy tắc đắt giá trong CLAUDE.md:
  §3.5 dùng `via_device_id` + `async_get_device_id_by_identifier` (API cũ chết ở 2027.8)
       — HA tự ném lỗi nếu code quay lại API cũ, nên test này chạy setup thật là đủ.
  §3.6 entity_id = slug(tên device) + slug(tên entity), không lặp tên device
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.luxcloud_ha import const
from custom_components.luxcloud_ha.switch import SWITCHES
from tests.conftest import setup_luxcloud

EXPECTED_ENTITY_IDS = {
    # ── inverter: sensor ──────────────────────────────────────
    "sensor.luxcloud_chu_ky_pin",
    "sensor.luxcloud_lech_cell",
    "sensor.luxcloud_cell_cao_nhat",
    "sensor.luxcloud_cell_thap_nhat",
    "sensor.luxcloud_nhiet_do_cell_cao_nhat",
    "sensor.luxcloud_nhiet_do_cell_thap_nhat",
    "sensor.luxcloud_trang_thai_bms",
    "sensor.luxcloud_ngo_ra_ac_pinv",
    "sensor.luxcloud_rectifier_prec",
    "sensor.luxcloud_su_co_gan_nhat",
    "sensor.luxcloud_co2_giam",
    "sensor.luxcloud_than_giam",
    "sensor.luxcloud_tuong_duong_cay",
    "sensor.luxcloud_ma_firmware_inverter",
    "sensor.luxcloud_firmware_moi_nhat",
    "sensor.luxcloud_chuoi_cong_suat_hom_nay",
    "sensor.luxcloud_tong_theo_nam",
    "sensor.luxcloud_bit_cau_hinh_hr_179_dang_bat",
    "sensor.luxcloud_trang_thai_quick_charge_discharge",
    "sensor.luxcloud_tong_san_luong_plant",
    # ── inverter: binary_sensor ───────────────────────────────
    "binary_sensor.luxcloud_su_co_dang_hieu_luc",
    "binary_sensor.luxcloud_cloud_co_du_lieu",
    "binary_sensor.luxcloud_dang_chay_quick_charge_discharge",
    "binary_sensor.luxcloud_co_firmware_moi",
    # Tên đổi 2026-09-30: "(isOffGrid)" → "(EPS)" vì key `isOffGrid` không tồn
    # tại trong payload runtime. Trên hệ thống ĐANG CHẠY, registry giữ
    # entity_id cũ `..._isoffgrid` (HA không đổi entity_id khi chỉ đổi name);
    # ở đây registry mới nên slug theo tên mới.
    "binary_sensor.luxcloud_dang_chay_khong_luoi_eps",
    # ── inverter: switch (3 bit HR[179]) ──────────────────────
    "switch.luxcloud_grid_peak_shaving",
    "switch.luxcloud_gen_peak_shaving",
    "switch.luxcloud_active_power_limit_mode",
    # ── inverter: button (quick charge/discharge) ─────────────
    "button.luxcloud_quick_charge_start",
    "button.luxcloud_quick_charge_stop",
    "button.luxcloud_quick_discharge_start",
    "button.luxcloud_quick_discharge_stop",
    # ── dongle ────────────────────────────────────────────────
    "sensor.luxcloud_dongle_firmware",
    "sensor.luxcloud_dongle_bao_cloud_lan_cuoi",
    "sensor.luxcloud_dongle_kieu_ket_noi",
    "binary_sensor.luxcloud_dongle_mat_ket_noi",
}


async def test_setup_entry_loads_and_registers_every_entity(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)

    assert entry.state is ConfigEntryState.LOADED
    ids = set(er.async_get(hass).entities)
    assert ids == EXPECTED_ENTITY_IDS, sorted(ids ^ EXPECTED_ENTITY_IDS)


async def test_entity_count_matches_the_documented_total(hass, patched_api) -> None:
    await setup_luxcloud(hass)
    assert len(er.async_get(hass).entities) == 36


async def test_switch_entities_are_exactly_the_non_overlapping_bits(hass, patched_api) -> None:
    """Chỉ 3 bit HR[179] có switch — các bit còn lại trùng entity Modbus local.

    Đây là quyết định thiết kế (tránh 2 nguồn ghi cùng một cấu hình), nên khoá
    lại bằng hành vi: đúng 3 switch, đúng tên, không thêm không bớt.
    """
    await setup_luxcloud(hass)

    switches = {
        entity_id
        for entity_id in er.async_get(hass).entities
        if entity_id.startswith("switch.")
    }
    assert switches == {
        "switch.luxcloud_grid_peak_shaving",
        "switch.luxcloud_gen_peak_shaving",
        "switch.luxcloud_active_power_limit_mode",
    }
    assert {desc.function_param for desc in SWITCHES} == {
        "FUNC_GRID_PEAK_SHAVING",
        "FUNC_GEN_PEAK_SHAVING",
        "FUNC_ACTIVE_POWER_LIMIT_MODE",
    }


async def _refresh_coordinator(hass, api) -> None:
    """Ép coordinator poll lại (mô phỏng nhịp poll kế tiếp)."""
    entry = hass.config_entries.async_entries("luxcloud_ha")[0]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_setup_entry_uses_the_configured_region(hass, patched_api) -> None:
    await setup_luxcloud(hass)
    assert patched_api.instances[-1].base_url == const.REGIONS["vn"]


async def test_setup_entry_fetches_slow_data_on_first_refresh(hass, patched_api) -> None:
    await setup_luxcloud(hass)
    assert patched_api.instances[-1].fetch_calls == [True]


async def test_device_registry_has_inverter_and_linked_dongle(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)

    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(devices) == 2

    by_name = {d.name: d for d in devices}
    assert set(by_name) == {const.DEVICE_NAME, const.DEVICE_NAME_DONGLE}

    dongle = by_name[const.DEVICE_NAME_DONGLE]
    parent = by_name[const.DEVICE_NAME]
    assert dongle.via_device_id == parent.id, "dongle phải nối vào inverter qua via_device_id"
    assert parent.via_device_id is None


async def test_no_entity_id_repeats_the_device_name(hass, patched_api) -> None:
    """Regression: đã từng ra `binary_sensor.luxcloud_dongle_dongle_mat_ket_noi`."""
    await setup_luxcloud(hass)

    for entity_id in er.async_get(hass).entities:
        object_id = entity_id.split(".", 1)[1]
        assert "luxcloud_dongle_dongle" not in object_id, entity_id
        assert object_id.count("luxcloud") == 1, entity_id


async def test_dongle_entities_belong_to_the_dongle_device(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)

    registry = dr.async_get(hass)
    devices = {d.name: d for d in dr.async_entries_for_config_entry(registry, entry.entry_id)}
    entity_registry = er.async_get(hass)

    dongle_entity = entity_registry.async_get("sensor.luxcloud_dongle_firmware")
    assert dongle_entity.device_id == devices[const.DEVICE_NAME_DONGLE].id

    inverter_entity = entity_registry.async_get("sensor.luxcloud_chu_ky_pin")
    assert inverter_entity.device_id == devices[const.DEVICE_NAME].id


async def test_unique_ids_are_serial_prefixed(hass, patched_api) -> None:
    await setup_luxcloud(hass)

    for entity in er.async_get(hass).entities.values():
        assert entity.unique_id.startswith("61204F0266_"), entity.unique_id


async def test_entities_report_the_fetched_values(hass, patched_api) -> None:
    await setup_luxcloud(hass)

    assert hass.states.get("sensor.luxcloud_chu_ky_pin").state == "54"
    assert hass.states.get("sensor.luxcloud_lech_cell").state == "4"
    assert hass.states.get("sensor.luxcloud_ma_firmware_inverter").state == "CHAA-000303"
    assert hass.states.get("sensor.luxcloud_trang_thai_bms").state == "Charging"
    assert hass.states.get("binary_sensor.luxcloud_co_firmware_moi").state == "on"


async def test_switches_start_off_because_every_bit_is_off(hass, patched_api) -> None:
    """Đo thật: cả 20 bit HR[179] đang tắt."""
    await setup_luxcloud(hass)

    for entity_id in (
        "switch.luxcloud_grid_peak_shaving",
        "switch.luxcloud_gen_peak_shaving",
        "switch.luxcloud_active_power_limit_mode",
    ):
        assert hass.states.get(entity_id).state == "off", entity_id


async def test_stop_buttons_are_unavailable_while_idle(hass, patched_api) -> None:
    """Task chưa chạy thì nút `stop` không có việc gì để làm."""
    await setup_luxcloud(hass)

    assert hass.states.get("button.luxcloud_quick_charge_start").state != "unavailable"
    assert hass.states.get("button.luxcloud_quick_charge_stop").state == "unavailable"
    assert hass.states.get("button.luxcloud_quick_discharge_start").state != "unavailable"
    assert hass.states.get("button.luxcloud_quick_discharge_stop").state == "unavailable"


async def test_stop_buttons_become_available_while_a_task_runs(hass, patched_api) -> None:
    await setup_luxcloud(hass)
    api = patched_api.instances[-1]

    api.data["quick"] = {**api.data["quick"], "charging": True, "charge_status": "WAIT_CHARGE"}
    await _refresh_coordinator(hass, api)

    assert hass.states.get("button.luxcloud_quick_charge_stop").state != "unavailable"
    assert hass.states.get("button.luxcloud_quick_charge_start").state == "unavailable"


async def test_unload_entry_removes_entities(hass, patched_api) -> None:
    entry = await setup_luxcloud(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
