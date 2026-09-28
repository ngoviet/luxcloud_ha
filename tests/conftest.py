"""Fixture dùng chung cho test của integration LuxCloud.

Dữ liệu mẫu ở đây mô phỏng ĐÚNG hình dạng response thật của cloud LuxPower
(đo trên tài khoản thật 2026-09-27/28) — kể cả những chỗ "kỳ quặc" đã từng
gây bug: `lost` là CHUỖI "False", nhiệt độ cell ×10, cell voltage là mV,
endpoint datalog KHÔNG có key `success`, tháng trong dayMultiLine 0-based.
"""
from __future__ import annotations

import sys

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

if sys.platform == "win32":
    # ── Workaround CHỈ dành cho Windows (không ảnh hưởng CI Linux) ──────────
    # PHACC gọi `pytest_socket.disable_socket()` trước MỖI test để chặn mạng.
    # Trên Linux asyncio dựng self-pipe của event loop bằng `AF_UNIX` (được
    # phép), nhưng Windows không có `AF_UNIX` nên `socket.socketpair()` rơi về
    # `AF_INET` → bị chặn → cả bộ test không chạy được (kể cả test thuần).
    # Vô hiệu hoá đúng lời gọi đó. An toàn vì test ở đây đều stub API cloud,
    # không test nào thực sự gọi mạng; trên Linux guard vẫn bật nguyên vẹn.
    import pytest_socket

    pytest_socket.disable_socket = lambda *args, **kwargs: None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Cho phép HA load `custom_components/luxcloud_ha` trong mọi test."""
    yield


# ── Response mẫu ───────────────────────────────────────────────


def plant_payload(
    *,
    fw_version: int = 3,
    standard: str = "CHAA",
    hardware_version: int = 12,
) -> dict:
    """`/api/plant/getPlantList` — có key `success` + `rows`."""
    return {
        "success": True,
        "rows": [
            {
                "plantId": 123456,
                "name": "Nhà anh Ngô",
                "statusLocaleText": "Normal",
                "todayYieldingText": "12.5 kWh",
                "totalYieldingText": "1997.4 kWh",
                "inverters": [
                    {
                        "standard": standard,
                        "fwVersion": fw_version,
                        "hardwareVersion": hardware_version,
                        "powerRating": 6,
                        "machineType": 6,
                        "protocolVersion": 2,
                        "model": "6.5kW",
                        "batteryType": "Lithium",
                    }
                ],
            }
        ],
    }


def runtime_payload(*, pinv: int = 1095, prec: int = 0, off_grid: bool = False) -> dict:
    return {
        "success": True,
        "hasRuntimeData": True,
        "pinv": pinv,
        "prec": prec,
        "isOffGrid": off_grid,
        "fwCode": "CHAA-000303",
        "lost": "False",
    }


def energy_payload() -> dict:
    return {
        "success": True,
        "hasTodayData": True,
        "fwCode": "CHAA-000303",
        "powerRatingText": "6.5kW",
        "totalCo2ReductionText": "1.99 Ton",
        "totalCoalReductionText": "798.96 kg",
        "totalTreeEquivalentText": "110.63 Trees",
    }


def datalog_payload(*, lost: str = "False") -> dict:
    """⚠️ KHÔNG có key `success` — chỉ có `rows`; `lost` là chuỗi."""
    return {
        "rows": [
            {
                "datalogSn": "DU61242846",
                "lost": lost,
                "lastUpdateTime": "2026-09-27 22:02:19",
                "firmwareVersion": "V2.11",
                "datalogType": "E",
                "datalogTypeText": "E Wi-Fi",
                "serverId": "5",
            }
        ]
    }


def event_payload(*, status: str = "CLOSE", text: str = "Pin mở") -> dict:
    return {
        "success": True,
        "rows": [
            {
                "recordId": 987,
                "event": "0x0A",
                "eventTypeText": "Battery",
                "eventText": text,
                "status": status,
                "startTime": "2026-09-27 21:40:00",
                "renormalTime": "2026-09-27 21:41:30",
            }
        ],
    }


def battery_payload(
    *,
    cell_max: int = 3381,
    cell_min: int = 3377,
    temp_max: int = 407,
    temp_min: int = 385,
) -> dict:
    """⚠️ cell voltage = mV; nhiệt độ = ×10; KHÔNG có `soh`."""
    return {
        "success": True,
        "bmsCycleCnt": 54,
        "globalMaxCellVoltage": cell_max,
        "globalMinCellVoltage": cell_min,
        "globalMaxCellTemp": temp_max,
        "globalMinCellTemp": temp_min,
        "batStatus": "Charging",
        "batPower": 1200,
        "hasCellExtremes": True,
    }


def quick_payload(*, charging: bool = False, discharging: bool = False) -> dict:
    return {
        "success": True,
        "hasUnclosedQuickChargeTask": charging,
        "hasUnclosedQuickDischargeTask": discharging,
        "unclosedQuickChargeTaskStatus": "WAIT_CHARGE" if charging else "",
        "unclosedQuickDischargeTaskStatus": "WAIT_DISCHARGE" if discharging else "",
        "remainTimeBeforeQuickChargeStop": 1800 if charging else 0,
        "remainTimeBeforeQuickDischargeStop": 900 if discharging else 0,
    }


def bits_payload(*enabled: str) -> dict:
    from custom_components.luxcloud_ha.const import CONFIG_BIT_KEYS

    payload = {"success": True}
    for key in CONFIG_BIT_KEYS:
        payload[key] = key in enabled
    return payload


def day_curve_payload(points: int = 223) -> dict:
    return {
        "success": True,
        "data": [
            {
                "time": f"{i // 60:02d}:{i % 60:02d}",
                "solarPv": 100 + i,
                "gridPower": i,
                "batteryDischarging": 0,
                "consumption": 200,
                "soc": 80,
            }
            for i in range(points)
        ],
    }


def total_column_payload() -> dict:
    """⚠️ đơn vị 0.1 kWh → phải chia 10."""
    return {
        "success": True,
        "data": [
            {
                "year": 2025,
                "ePv1Day": 10000,
                "ePv2Day": 2000,
                "ePv3Day": 0,
                "eToUserDay": 5000,
                "eToGridDay": 1000,
                "eConsumptionDay": 8000,
            },
            {
                "year": 2026,
                "ePv1Day": 18000,
                "ePv2Day": 1740,
                "eToUserDay": 9000,
                "eToGridDay": 2000,
                "eConsumptionDay": 15000,
            },
        ],
    }


def firmware_rows(standard: str, versions: tuple[int, int, int]) -> dict:
    v1, v2, v3 = versions
    return {
        "rows": [
            {
                "fileName": f"{standard}-{v1:02d}{v2:02d}{v3:02d}.bin",
                "standard": standard,
                "v1": v1,
                "v2": v2,
                "v3": v3,
                "recordId": 1,
            }
        ]
    }


def full_dataset(*, fw_version: int = 3, lost: str = "False") -> dict:
    """Bộ dữ liệu đã chuẩn hoá — dùng để test value_fn của entity."""
    return {
        "plant": {
            "plant_id": 123456,
            "plant_name": "Nhà anh Ngô",
            "status_text": "Normal",
            "today_yielding_text": "12.5 kWh",
            "total_yielding_text": "1997.4 kWh",
            "standard": "CHAA",
            "fw_version": fw_version,
            "hardware_version": 12,
            "power_rating": 6,
            "machine_type": 6,
            "protocol_version": 2,
            "model": "6.5kW",
            "battery_type": "Lithium",
        },
        "runtime": {"pinv": 1095, "prec": 0, "isOffGrid": False, "fwCode": "CHAA-000303"},
        "energy": {"hasTodayData": True, "fwCode": "CHAA-000303"},
        "dongle": {
            "sn": "DU61242846",
            "lost": lost == "True",
            "last_update": "2026-09-27 22:02:19",
            "firmware": "V2.11",
            "type": "E",
            "type_text": "E Wi-Fi",
            "server_id": "5",
        },
        "event": {
            "record_id": 987,
            "code": "0x0A",
            "type_text": "Battery",
            "text": "Pin mở",
            "status": "CLOSE",
            "start": "2026-09-27 21:40:00",
            "renormal": "2026-09-27 21:41:30",
            "count": 1,
            "recent": [],
        },
        "battery": {
            "cycles": 54,
            "cell_max_mv": 3381,
            "cell_min_mv": 3377,
            "cell_delta_mv": 4,
            "cell_max_temp_c": 40.7,
            "cell_min_temp_c": 38.5,
            "status": "Charging",
            "power_w": 1200,
            "has_cell_extremes": True,
        },
        "quick": {
            "charging": False,
            "discharging": False,
            "charge_status": "",
            "discharge_status": "",
            "remain_charge_s": 0,
            "remain_discharge_s": 0,
        },
        "bits": {"FUNC_GRID_PEAK_SHAVING": True, "FUNC_RSD_DISABLE": False},
        "green": {"co2_ton": 1.99, "coal_kg": 798.96, "trees": 110.63},
        "health": {
            "cloud_ok": True,
            "has_runtime": True,
            "has_today": True,
            "lost": False,
            "pinv": 1095,
            "prec": 0,
            "fw_code": "CHAA-000303",
            "power_rating": "6.5kW",
        },
        "firmware": {
            "device_type": "SNA3_6K_EU",
            "count": 9,
            "matched": 1,
            "latest_version": 8,
            "items": [{"file": "CHAA-000800.bin"}],
        },
        "day_curve": {"date": "2026-09-28", "count": 72, "points": []},
        "total_years": {
            "2026": {"pv": 1974.0, "import": 900.0, "export": 200.0, "consumption": 1500.0}
        },
    }
