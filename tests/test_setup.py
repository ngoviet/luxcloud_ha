"""Test setup đầy đủ: entry được load, 29 entity, và liên kết device dongle→inverter.

Đây là test bắt regression cho hai quy tắc đắt giá trong CLAUDE.md:
  §3.5 dùng `via_device_id` + `async_get_device_id_by_identifier` (API cũ chết ở 2027.8)
  §3.6 entity_id = slug(tên device) + slug(tên entity), không lặp tên device
"""
from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxcloud_ha import const
from tests.conftest import full_dataset


class _FakeApi:
    """Thay `LuxCloudApi` trong lúc setup — không gọi mạng."""

    instances: list["_FakeApi"] = []

    def __init__(self, session, base_url, account, password, serial) -> None:
        self.base_url = base_url
        self.account = account
        self.serial = serial.upper()
        self.plant_id = 123456
        self.user_id = 42
        self.login_calls = 0
        self.fetch_calls: list[bool] = []
        _FakeApi.instances.append(self)

    async def login(self) -> bool:
        self.login_calls += 1
        return True

    async def async_fetch_all(self, slow: bool, date_text: str) -> dict:
        self.fetch_calls.append(slow)
        return full_dataset()


@pytest.fixture
def patched_api(monkeypatch):
    _FakeApi.instances.clear()
    monkeypatch.setattr("custom_components.luxcloud_ha.LuxCloudApi", _FakeApi)
    return _FakeApi


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=const.DOMAIN,
        title="LuxCloud 61204F0266",
        data={
            const.CONF_ACCOUNT: "u@example.com",
            const.CONF_PASSWORD: "pw",
            const.CONF_SERIAL: "61204F0266",
            const.CONF_REGION: "vn",
        },
        options={
            const.CONF_SCAN_INTERVAL: 300,
            const.CONF_ENABLE_SERIES: True,
            const.CONF_ENABLE_FIRMWARE: True,
        },
        unique_id="61204F0266",
    )


async def test_setup_entry_loads_and_registers_29_entities(hass, patched_api) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    entity_ids = er.async_get(hass).entities
    assert len(entity_ids) == 29, sorted(entity_ids)


async def test_setup_entry_uses_the_configured_region(hass, patched_api) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert patched_api.instances[-1].base_url == const.REGIONS["vn"]


async def test_setup_entry_fetches_slow_data_on_first_refresh(hass, patched_api) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert patched_api.instances[-1].fetch_calls == [True]


async def test_device_registry_has_inverter_and_linked_dongle(hass, patched_api) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(devices) == 2

    by_name = {d.name: d for d in devices}
    assert set(by_name) == {const.DEVICE_NAME, const.DEVICE_NAME_DONGLE}

    dongle = by_name[const.DEVICE_NAME_DONGLE]
    parent = by_name[const.DEVICE_NAME]
    assert dongle.via_device_id == parent.id, "dongle phải nối vào inverter qua via_device_id"
    assert parent.via_device_id is None


async def test_entity_ids_follow_device_plus_entity_naming(hass, patched_api) -> None:
    """Các id ĐO THẬT trên HA 2026.9.4 — lệch nghĩa là đã đổi tên entity."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    ids = set(er.async_get(hass).entities)
    for expected in (
        "sensor.luxcloud_chu_ky_pin",
        "sensor.luxcloud_lech_cell",
        "sensor.luxcloud_cell_cao_nhat",
        "sensor.luxcloud_nhiet_do_cell_cao_nhat",
        "sensor.luxcloud_ma_firmware_inverter",
        "sensor.luxcloud_su_co_gan_nhat",
        "sensor.luxcloud_bit_cau_hinh_hr_179_dang_bat",
        "sensor.luxcloud_dongle_firmware",
        "binary_sensor.luxcloud_su_co_dang_hieu_luc",
        "binary_sensor.luxcloud_dongle_mat_ket_noi",
    ):
        assert expected in ids, f"thiếu {expected}"


async def test_no_entity_id_repeats_the_device_name(hass, patched_api) -> None:
    """Regression: đã từng ra `binary_sensor.luxcloud_dongle_dongle_mat_ket_noi`."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for entity_id in er.async_get(hass).entities:
        object_id = entity_id.split(".", 1)[1]
        assert "luxcloud_dongle_dongle" not in object_id, entity_id
        assert object_id.count("luxcloud") == 1, entity_id


async def test_dongle_entities_belong_to_the_dongle_device(hass, patched_api) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    devices = {
        d.name: d for d in dr.async_entries_for_config_entry(registry, entry.entry_id)
    }
    entity_registry = er.async_get(hass)

    dongle_entity = entity_registry.async_get("sensor.luxcloud_dongle_firmware")
    assert dongle_entity.device_id == devices[const.DEVICE_NAME_DONGLE].id

    inverter_entity = entity_registry.async_get("sensor.luxcloud_chu_ky_pin")
    assert inverter_entity.device_id == devices[const.DEVICE_NAME].id


async def test_unique_ids_are_serial_prefixed(hass, patched_api) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for entity in er.async_get(hass).entities.values():
        assert entity.unique_id.startswith("61204F0266_"), entity.unique_id


async def test_entities_report_the_fetched_values(hass, patched_api) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.luxcloud_chu_ky_pin").state == "54"
    assert hass.states.get("sensor.luxcloud_lech_cell").state == "4"
    assert hass.states.get("sensor.luxcloud_ma_firmware_inverter").state == "CHAA-000303"
    assert hass.states.get("sensor.luxcloud_trang_thai_bms").state == "Charging"
    assert hass.states.get("binary_sensor.luxcloud_co_firmware_moi").state == "on"


async def test_unload_entry_removes_entities(hass, patched_api) -> None:
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
