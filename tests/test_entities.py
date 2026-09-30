"""Test entity đọc: value_fn của sensor + is_on_fn của binary_sensor.

Test trực tiếp hàm lấy giá trị trong bảng mô tả (không dựng entity), vì đó mới
là chỗ chứa logic; phần khung entity là của HA.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.luxcloud_ha.binary_sensor import BINARY_SENSORS, LuxCloudBinarySensor
from custom_components.luxcloud_ha.sensor import SENSORS
from tests.conftest import full_dataset

SENSOR_BY_KEY = {d.key: d for d in SENSORS}
BINARY_BY_KEY = {d.key: d for d in BINARY_SENSORS}


def value(key: str, data: dict):
    return SENSOR_BY_KEY[key].value_fn(data)


def is_on(key: str, data: dict) -> bool:
    return bool(BINARY_BY_KEY[key].is_on_fn(data))


def attrs_for(key: str, data: dict) -> dict:
    desc = BINARY_BY_KEY[key]
    assert desc.attrs_fn is not None, f"{key} thiếu attrs_fn"
    return desc.attrs_fn(data)


# ── Cấu trúc bảng mô tả ────────────────────────────────────────


def test_entity_counts_match_the_documented_baseline() -> None:
    """Baseline Phase 1: 29 entity = 23 sensor + 6 binary_sensor."""
    assert len(SENSORS) == 23
    assert len(BINARY_SENSORS) == 6
    assert len(SENSORS) + len(BINARY_SENSORS) == 29


def test_entity_keys_are_unique() -> None:
    keys = [d.key for d in SENSORS] + [d.key for d in BINARY_SENSORS]
    assert len(keys) == len(set(keys))


def test_unique_id_scheme_is_serial_plus_key() -> None:
    """unique_id = f"{serial}_{key}" → đổi tên entity không làm mất lịch sử."""
    entity = LuxCloudBinarySensor.__new__(LuxCloudBinarySensor)
    entity.entity_description = BINARY_BY_KEY["dongle_lost"]
    entity._attr_unique_id = "61204F0266_dongle_lost"
    assert entity.unique_id == "61204F0266_dongle_lost"


def test_dongle_flag_is_only_set_on_dongle_entities() -> None:
    dongle_sensors = {d.key for d in SENSORS if d.dongle}
    dongle_binary = {d.key for d in BINARY_SENSORS if d.dongle}
    assert dongle_sensors == {"dongle_firmware", "dongle_last_report", "dongle_type"}
    assert dongle_binary == {"dongle_lost"}


def test_every_entity_has_a_name() -> None:
    for desc in (*SENSORS, *BINARY_SENSORS):
        assert desc.name, f"{desc.key} thiếu name"


# ── Sensor: dongle ─────────────────────────────────────────────


def test_dongle_firmware_and_type() -> None:
    data = full_dataset()
    assert value("dongle_firmware", data) == "V2.11"
    assert value("dongle_type", data) == "E Wi-Fi"


def test_dongle_type_falls_back_to_raw_code() -> None:
    data = full_dataset()
    data["dongle"]["type_text"] = ""
    assert value("dongle_type", data) == "E"


def test_dongle_last_report_is_timezone_aware() -> None:
    """device_class=timestamp → HA cần datetime có tz, không phải chuỗi."""
    result = value("dongle_last_report", full_dataset())
    assert result is not None
    assert result.tzinfo is not None
    assert (result.year, result.month, result.day) == (2026, 9, 27)


@pytest.mark.parametrize("bad", ["", "không-phải-ngày", None])
def test_dongle_last_report_returns_none_on_garbage(bad) -> None:
    data = full_dataset()
    data["dongle"]["last_update"] = bad
    assert value("dongle_last_report", data) is None


def test_dongle_firmware_none_when_absent() -> None:
    assert value("dongle_firmware", {}) is None
    assert value("dongle_last_report", {}) is None


# ── Sensor: sự cố ──────────────────────────────────────────────


def test_event_latest_exposes_history_in_attributes() -> None:
    data = full_dataset()
    assert value("event_latest", data) == "Pin mở"
    attrs = SENSOR_BY_KEY["event_latest"].attrs_fn(data)
    assert attrs["status"] == "CLOSE"
    assert attrs["code"] == "0x0A"
    assert attrs["recent"] == []


def test_event_latest_none_when_no_event() -> None:
    assert value("event_latest", {}) is None


# ── Sensor: pin / BMS ──────────────────────────────────────────


def test_battery_sensors_pass_through_normalised_values() -> None:
    data = full_dataset()
    assert value("bms_cycles", data) == 54
    assert value("bms_cell_delta", data) == 4
    assert value("bms_cell_max_voltage", data) == 3381
    assert value("bms_cell_min_voltage", data) == 3377
    assert value("bms_cell_max_temp", data) == 40.7
    assert value("bms_cell_min_temp", data) == 38.5
    assert value("bms_status", data) == "Charging"


def test_bms_status_none_when_absent() -> None:
    assert value("bms_status", {}) is None


def test_bms_units_are_declared_correctly() -> None:
    """mV cho cell, °C cho nhiệt độ — sai đơn vị là sai số liệu hiển thị."""
    assert SENSOR_BY_KEY["bms_cell_delta"].native_unit_of_measurement == "mV"
    assert SENSOR_BY_KEY["bms_cell_max_temp"].native_unit_of_measurement == "°C"


# ── Sensor: công suất + năng lượng xanh ────────────────────────


def test_power_sensors() -> None:
    data = full_dataset()
    assert value("ac_output", data) == 1095
    assert value("rectifier", data) == 0


def test_green_sensors() -> None:
    data = full_dataset()
    assert value("co2_reduction", data) == 1.99
    assert value("coal_reduction", data) == 798.96
    assert value("tree_equivalent", data) == 110.63


def test_plant_total_yield_parses_unit_text() -> None:
    """Cloud trả '1997.4 kWh' — sensor phải ra số 1997.4."""
    assert value("plant_total_yield", full_dataset()) == 1997.4


def test_plant_total_yield_none_for_placeholder() -> None:
    data = full_dataset()
    data["plant"]["total_yielding_text"] = "--"
    assert value("plant_total_yield", data) is None


# ── Sensor: firmware ───────────────────────────────────────────


def test_firmware_code_and_latest_version() -> None:
    data = full_dataset()
    assert value("inverter_fw_code", data) == "CHAA-000303"
    assert value("firmware_latest", data) == 8


def test_firmware_code_none_when_cloud_silent() -> None:
    assert value("inverter_fw_code", {}) is None


def test_firmware_code_attributes_carry_device_identity() -> None:
    attrs = SENSOR_BY_KEY["inverter_fw_code"].attrs_fn(full_dataset())
    assert attrs["plant_standard"] == "CHAA"
    assert attrs["plant_fw_version"] == 3
    assert attrs["hardware_version"] == 12


# ── Sensor: chuỗi ngày / năm ───────────────────────────────────


def test_day_curve_count_and_attributes() -> None:
    data = full_dataset()
    assert value("day_curve", data) == 72
    assert SENSOR_BY_KEY["day_curve"].attrs_fn(data)["date"] == "2026-09-28"


def test_total_by_year_picks_the_current_year() -> None:
    from homeassistant.util import dt as dt_util

    data = full_dataset()
    year = str(dt_util.now().year)
    data["total_years"] = {year: {"pv": 1974.0}}
    assert value("total_by_year", data) == 1974.0


def test_total_by_year_none_when_year_missing() -> None:
    data = full_dataset()
    data["total_years"] = {"1999": {"pv": 1.0}}
    assert value("total_by_year", data) is None


# ── Sensor: chẩn đoán ──────────────────────────────────────────


def test_config_bits_counts_enabled_bits() -> None:
    data = full_dataset()
    data["bits"] = {"A": True, "B": False, "C": True}
    assert value("config_bits", data) == 2


def test_config_bits_zero_when_none_enabled() -> None:
    data = full_dataset()
    data["bits"] = {}
    assert value("config_bits", data) == 0
    assert SENSOR_BY_KEY["config_bits"].attrs_fn(data) == {"bits": {}}


@pytest.mark.parametrize(
    ("quick", "expected"),
    [
        ({"charging": False, "discharging": False, "charge_status": "", "discharge_status": ""}, "idle"),
        ({"charging": True, "charge_status": "WAIT_CHARGE", "discharge_status": ""}, "WAIT_CHARGE"),
        ({"charging": False, "charge_status": "", "discharge_status": "WAIT_DISCHARGE"}, "WAIT_DISCHARGE"),
        ({"charging": True, "charge_status": "", "discharge_status": ""}, "charging"),
    ],
)
def test_quick_state_resolution(quick: dict, expected: str) -> None:
    data = full_dataset()
    data["quick"] = quick
    assert value("quick_state", data) == expected


# ── Binary sensor ──────────────────────────────────────────────


def test_dongle_lost_flag() -> None:
    assert is_on("dongle_lost", full_dataset(lost="False")) is False
    assert is_on("dongle_lost", full_dataset(lost="True")) is True
    assert is_on("dongle_lost", {}) is False


def test_event_active_is_false_for_closed_events() -> None:
    """`status` = CLOSE nghĩa là đã khỏi → không phải sự cố đang hiệu lực."""
    assert is_on("event_active", full_dataset()) is False


@pytest.mark.parametrize("status", ["OPEN", "ACTIVE", "wait", "1"])
def test_event_active_is_true_for_open_events(status: str) -> None:
    data = full_dataset()
    data["event"]["status"] = status
    assert is_on("event_active", data) is True


def test_event_active_missing_status_defaults_to_closed() -> None:
    assert is_on("event_active", {}) is False


def test_event_active_is_case_insensitive() -> None:
    data = full_dataset()
    data["event"]["status"] = "close"
    assert is_on("event_active", data) is False


def test_cloud_data_ok_requires_both_flags() -> None:
    data = full_dataset()
    assert is_on("cloud_data_ok", data) is True
    data["health"]["has_runtime"] = False
    assert is_on("cloud_data_ok", data) is False
    data = full_dataset()
    data["health"]["cloud_ok"] = False
    assert is_on("cloud_data_ok", data) is False


def test_quick_task_active_for_charge_or_discharge() -> None:
    assert is_on("quick_task_active", full_dataset()) is False
    data = full_dataset()
    data["quick"]["charging"] = True
    assert is_on("quick_task_active", data) is True
    data = full_dataset()
    data["quick"]["discharging"] = True
    assert is_on("quick_task_active", data) is True


def test_off_grid_flag() -> None:
    """status=0xC0 (PV+pin gánh EPS) ⇒ đang chạy không lưới."""
    assert is_on("off_grid", full_dataset()) is False
    data = full_dataset()
    data["runtime"]["status"] = 192
    assert is_on("off_grid", data) is True


def test_off_grid_flag_regression_isoffgrid_key() -> None:
    """Hồi quy 2026-09-30: key `isOffGrid` KHÔNG có trong payload thật.

    Bản cũ đọc key này nên cờ luôn `off` dù mất lưới. Test này khoá lại:
    chỉ `isOffGrid` (không có `status`) ⇒ dự phòng theo vacr/fac.
    """
    data = full_dataset()
    rt = data["runtime"]
    rt.pop("status", None)
    rt["vacr"] = 0
    rt["fac"] = 0
    rt["isOffGrid"] = True
    assert is_on("off_grid", data) is True

    # Có lưới (221.7 V / 50.15 Hz) mà status thiếu ⇒ KHÔNG báo mất lưới.
    data2 = full_dataset()
    rt2 = data2["runtime"]
    rt2.pop("status", None)
    rt2["vacr"] = 2217
    rt2["fac"] = 5015
    assert is_on("off_grid", data2) is False


def test_off_grid_attributes_expose_evidence() -> None:
    data = full_dataset()
    data["runtime"].update({"status": 192, "peps": 1262, "vacr": 0, "fac": 0})
    attrs = attrs_for("off_grid", data)
    assert attrs["status"] == 192
    assert attrs["eps_power_w"] == 1262
    assert "0xC0" in attrs["note"]


# ── Có firmware mới (caveat §9) ────────────────────────────────


def test_firmware_available_when_catalogue_is_newer() -> None:
    """Đo thật: catalog 8 > fwVersion 3 → bật (kèm attribute `caveat`)."""
    assert is_on("firmware_available", full_dataset(fw_version=3)) is True


def test_firmware_available_false_when_equal_or_older() -> None:
    assert is_on("firmware_available", full_dataset(fw_version=8)) is False
    data = full_dataset(fw_version=9)
    assert is_on("firmware_available", data) is False


def test_firmware_available_false_when_catalogue_missing() -> None:
    data = full_dataset()
    data["firmware"] = {}
    assert is_on("firmware_available", data) is False


def test_firmware_attributes_document_the_caveat() -> None:
    """Check firmware chỉ là GỢI Ý — attribute phải nói rõ (CLAUDE.md §9)."""
    attrs = BINARY_BY_KEY["firmware_available"].attrs_fn(full_dataset())
    assert attrs["device_fw_version"] == 3
    assert attrs["latest_fw_version"] == 8
    assert "caveat" in attrs
    assert "CHAA-000303" in attrs["caveat"]
    assert "xác nhận trong app" in attrs["caveat"]


def test_firmware_available_survives_malformed_versions() -> None:
    """`is_on` bọc try/except TypeError/ValueError → không được ném ra HA."""
    entity = LuxCloudBinarySensor.__new__(LuxCloudBinarySensor)
    entity.entity_description = BINARY_BY_KEY["firmware_available"]
    entity.coordinator = SimpleNamespace(
        data={"plant": {"fw_version": 3}, "firmware": {"latest_version": "abc"}}
    )
    assert entity.is_on is False
