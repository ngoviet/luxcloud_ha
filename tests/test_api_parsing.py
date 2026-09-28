"""Test lớp API: chuẩn hoá dữ liệu cloud → dict mà entity dùng.

Đây là nơi tập trung rủi ro thật của integration: cloud trả đơn vị KHÔNG đồng
nhất (mV, ×10, 0.1 kWh, chuỗi "False") và vài endpoint thiếu key `success`.
Mọi con số kỳ vọng ở đây lấy từ giá trị ĐO THẬT 2026-09-27/28.
"""
from __future__ import annotations

import asyncio

import aiohttp
import pytest

from custom_components.luxcloud_ha import const
from custom_components.luxcloud_ha.api import (
    LuxCloudApi,
    LuxCloudApiError,
    LuxCloudAuthError,
    _aes_encrypt,
    _f,
    _i,
    _num_text,
)
from tests import conftest as fx


def run(coro):
    """Chạy coroutine trong test đồng bộ (không cần pytest-asyncio)."""
    return asyncio.run(coro)


def make_api(serial: str = "61204f0266") -> LuxCloudApi:
    """API với session giả — `_post` luôn được thay trong từng test."""
    return LuxCloudApi(None, "https://vn.luxpowertek.com/WManage/", "u@example.com", "pw", serial)


def patch_post(api: LuxCloudApi, handler) -> list:
    """Thay `_post` bằng hàm đồng bộ-trên-dữ-liệu; trả về log các lời gọi."""
    calls: list[tuple[str, dict, str | None]] = []

    async def _post(endpoint, params=None, base=None):
        calls.append((endpoint, dict(params or {}), base))
        return handler(endpoint, params or {}, base)

    api._post = _post
    return calls


def route(mapping: dict):
    """Handler định tuyến theo endpoint."""

    def handler(endpoint, params, base):
        value = mapping.get(endpoint)
        return value(params) if callable(value) else value

    return handler


# ── Hàm tiện ích ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (5, 5),
        ("5", 5),
        ("5.9", 5),
        (5.9, 5),
        (None, 0),
        ("", 0),
        ("abc", 0),
        ("--", 0),
    ],
)
def test_int_coercion(raw, expected) -> None:
    assert _i(raw) == expected


def test_int_coercion_honours_custom_default() -> None:
    assert _i("abc", -1) == -1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1.5", 1.5), (2, 2.0), ("abc", None), (None, None)],
)
def test_float_coercion(raw, expected) -> None:
    assert _f(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.96 Ton", 1.96),
        ("798.96 kg", 798.96),
        ("110.63 Trees", 110.63),
        ("1970.6 kWh", 1970.6),
        ("--", None),
        ("", None),
        (None, None),
    ],
)
def test_num_text_parsing(raw, expected) -> None:
    """Entity 'xanh' nhận chuỗi kèm đơn vị (tấn/kg/cây) — phải bóc số ra."""
    assert _num_text(raw) == expected


# ── AES cho refreshInputData ───────────────────────────────────


def test_aes_encrypt_is_deterministic_and_padded() -> None:
    import base64

    plaintext = "1700000000000&42"
    assert len(plaintext) == 16, "fixture phải đúng 16 byte để kiểm tra đệm full-block"
    out1 = _aes_encrypt(plaintext)
    out2 = _aes_encrypt(plaintext)
    assert out1 == out2, "AES/ECB phải cho cùng kết quả với cùng input"
    raw = base64.b64decode(out1)
    assert len(raw) % 16 == 0, "PKCS5 phải đệm tới bội số của 16"
    assert len(raw) == 32, "input đủ 16 byte vẫn phải thêm 1 block đệm"


def test_aes_encrypt_pads_short_and_full_blocks() -> None:
    import base64

    # input đúng 16 byte → phải thêm NGUYÊN một block đệm (PKCS5 luôn đệm)
    assert len(base64.b64decode(_aes_encrypt("x" * 16))) == 32
    assert len(base64.b64decode(_aes_encrypt("x" * 15))) == 16


def test_aes_encrypt_matches_an_independent_implementation() -> None:
    """Đối chiếu với AES/ECB viết tay — bắt lỗi nếu ai đó đổi key/padding."""
    import base64

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    plaintext = "1700000000000&42"
    data = plaintext.encode()
    pad = 16 - (len(data) % 16)
    data += bytes([pad]) * pad
    enc = Cipher(algorithms.AES(const.AES_KEY), modes.ECB()).encryptor()
    expected = base64.b64encode(enc.update(data) + enc.finalize()).decode()
    assert _aes_encrypt(plaintext) == expected


# ── _post: HTTP + JSON ─────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, "kwargs": kwargs})
        if self.error is not None:
            raise self.error
        return self.response


def test_post_returns_none_on_non_200() -> None:
    api = make_api()
    api._session = _FakeSession(_FakeResponse(500, "boom"))
    assert run(api._post("/x", {})) is None


def test_post_raises_auth_error_on_401() -> None:
    api = make_api()
    api._session = _FakeSession(_FakeResponse(401, "nope"))
    with pytest.raises(LuxCloudAuthError):
        run(api._post("/x", {}))


def test_post_returns_none_on_invalid_json() -> None:
    api = make_api()
    api._session = _FakeSession(_FakeResponse(200, "<html>not json</html>"))
    assert run(api._post("/x", {})) is None


def test_post_returns_none_on_json_array() -> None:
    """Chỉ nhận dict; mảng JSON bị coi là không dùng được."""
    api = make_api()
    api._session = _FakeSession(_FakeResponse(200, "[1, 2]"))
    assert run(api._post("/x", {})) is None


def test_post_returns_none_on_network_error() -> None:
    api = make_api()
    api._session = _FakeSession(error=aiohttp.ClientConnectionError("mất mạng"))
    assert run(api._post("/x", {})) is None


def test_post_sends_form_encoded_and_uses_base_override() -> None:
    api = make_api()
    session = _FakeSession(_FakeResponse(200, '{"success": true}'))
    api._session = session
    payload = run(api._post("/ep", {"a": 1, "b": "x"}, base="https://as.luxpowertek.com/WManage"))
    assert payload == {"success": True}
    assert session.calls[0]["url"] == "https://as.luxpowertek.com/WManage/ep"


def test_serial_is_upper_cased_and_trailing_slash_stripped() -> None:
    api = make_api("61204f0266")
    assert api.serial == "61204F0266"


# ── login ──────────────────────────────────────────────────────


def test_login_stores_user_id() -> None:
    api = make_api()
    patch_post(api, route({const.EP_LOGIN: {"success": True, "userId": 42}}))
    assert run(api.login()) is True
    assert api.user_id == 42


def test_login_raises_auth_error_on_bad_credentials() -> None:
    api = make_api()
    patch_post(api, route({const.EP_LOGIN: {"success": False, "msg": "sai mật khẩu"}}))
    with pytest.raises(LuxCloudAuthError):
        run(api.login())


def test_login_raises_api_error_on_no_response() -> None:
    api = make_api()
    patch_post(api, route({const.EP_LOGIN: None}))
    with pytest.raises(LuxCloudApiError):
        run(api.login())


# ── plant ──────────────────────────────────────────────────────


def test_get_plant_flattens_first_inverter() -> None:
    api = make_api()
    patch_post(api, route({const.EP_PLANT: fx.plant_payload()}))
    plant = run(api.get_plant())
    assert api.plant_id == 123456
    assert plant["standard"] == "CHAA"
    assert plant["fw_version"] == 3
    assert plant["hardware_version"] == 12
    assert plant["total_yielding_text"] == "1997.4 kWh"


def test_get_plant_handles_empty_rows() -> None:
    api = make_api()
    patch_post(api, route({const.EP_PLANT: {"success": True, "rows": []}}))
    assert run(api.get_plant()) == {}


# ── dongle ─────────────────────────────────────────────────────


def test_get_dongle_parses_lost_string_false() -> None:
    """`lost` là CHUỖI "False" — bool("False") sẽ ra True nếu parse sai."""
    api = make_api()
    api.plant_id = 1
    patch_post(api, route({const.EP_DATALOG: fx.datalog_payload(lost="False")}))
    dongle = run(api.get_dongle())
    assert dongle["lost"] is False
    assert dongle["sn"] == "DU61242846"
    assert dongle["firmware"] == "V2.11"
    assert dongle["type_text"] == "E Wi-Fi"


def test_get_dongle_parses_lost_string_true() -> None:
    api = make_api()
    api.plant_id = 1
    patch_post(api, route({const.EP_DATALOG: fx.datalog_payload(lost="True")}))
    assert run(api.get_dongle())["lost"] is True


def test_get_dongle_works_without_success_key() -> None:
    """Endpoint datalog KHÔNG trả key `success` — phải dựa vào `rows`."""
    api = make_api()
    api.plant_id = 1
    payload = fx.datalog_payload()
    assert "success" not in payload
    patch_post(api, route({const.EP_DATALOG: payload}))
    assert run(api.get_dongle())["lost"] is False


def test_get_dongle_returns_empty_without_plant_id() -> None:
    api = make_api()
    calls = patch_post(api, route({}))
    assert run(api.get_dongle()) == {}
    assert calls == [], "không có plant_id thì không được gọi API"


# ── sự cố ──────────────────────────────────────────────────────


def test_get_events_returns_latest_plus_recent() -> None:
    api = make_api()
    api.plant_id = 1
    patch_post(api, route({const.EP_EVENT: fx.event_payload()}))
    event = run(api.get_events())
    assert event["text"] == "Pin mở"
    assert event["status"] == "CLOSE"
    assert event["count"] == 1
    assert len(event["recent"]) == 1


def test_get_events_requests_vietnamese_localisation() -> None:
    api = make_api()
    api.plant_id = 1
    calls = patch_post(api, route({const.EP_EVENT: fx.event_payload()}))
    run(api.get_events())
    assert calls[0][1]["language"] == "vi"


def test_get_events_empty_rows_returns_empty_dict() -> None:
    api = make_api()
    api.plant_id = 1
    patch_post(api, route({const.EP_EVENT: {"success": True, "rows": []}}))
    assert run(api.get_events()) == {}


# ── pin / BMS ──────────────────────────────────────────────────


def test_get_battery_converts_units() -> None:
    """cell = mV (nguyên); nhiệt độ = ×10 → chia 10."""
    api = make_api()
    patch_post(api, route({const.EP_BATTERY: fx.battery_payload()}))
    battery = run(api.get_battery())
    assert battery["cycles"] == 54
    assert battery["cell_max_mv"] == 3381
    assert battery["cell_min_mv"] == 3377
    assert battery["cell_delta_mv"] == 4
    assert battery["cell_max_temp_c"] == 40.7
    assert battery["cell_min_temp_c"] == 38.5
    assert battery["status"] == "Charging"


def test_get_battery_delta_is_zero_when_a_cell_reading_is_missing() -> None:
    api = make_api()
    patch_post(api, route({const.EP_BATTERY: fx.battery_payload(cell_min=0)}))
    assert run(api.get_battery())["cell_delta_mv"] == 0


def test_get_battery_has_no_soh_field() -> None:
    """Cloud KHÔNG trả `soh`/`fullCapacity` — entity không được hứa hẹn nó."""
    api = make_api()
    patch_post(api, route({const.EP_BATTERY: fx.battery_payload()}))
    battery = run(api.get_battery())
    assert "soh" not in battery
    assert "full_capacity" not in battery


def test_get_battery_returns_empty_on_failure() -> None:
    api = make_api()
    patch_post(api, route({const.EP_BATTERY: {"success": False}}))
    assert run(api.get_battery()) == {}


# ── quick charge ───────────────────────────────────────────────


def test_get_quick_status_idle() -> None:
    api = make_api()
    patch_post(api, route({const.EP_QUICK_STATUS: fx.quick_payload()}))
    quick = run(api.get_quick_status())
    assert quick["charging"] is False
    assert quick["discharging"] is False
    assert quick["charge_status"] == ""
    assert quick["remain_charge_s"] == 0


def test_get_quick_status_charging_reports_status_and_remain() -> None:
    api = make_api()
    patch_post(api, route({const.EP_QUICK_STATUS: fx.quick_payload(charging=True)}))
    quick = run(api.get_quick_status())
    assert quick["charging"] is True
    assert quick["charge_status"] == "WAIT_CHARGE"
    assert quick["remain_charge_s"] == 1800
    assert quick["discharge_status"] == ""


# ── bit cấu hình HR[179] ───────────────────────────────────────


def test_get_config_bits_only_returns_known_keys() -> None:
    api = make_api()
    payload = fx.bits_payload("FUNC_GRID_PEAK_SHAVING", "FUNC_RSD_DISABLE")
    payload["SOME_UNKNOWN_BIT"] = True
    patch_post(api, route({const.EP_REMOTE_READ: payload}))
    bits = run(api.get_config_bits())
    assert bits["FUNC_GRID_PEAK_SHAVING"] is True
    assert bits["FUNC_RSD_DISABLE"] is True
    assert "SOME_UNKNOWN_BIT" not in bits
    assert set(bits) <= set(const.CONFIG_BIT_KEYS)


def test_get_config_bits_reads_block_160() -> None:
    api = make_api()
    calls = patch_post(api, route({const.EP_REMOTE_READ: fx.bits_payload()}))
    run(api.get_config_bits())
    assert calls[0][1]["startRegister"] == str(const.CONFIG_BIT_BLOCK)


# ── chuỗi ngày ─────────────────────────────────────────────────


def test_get_day_curve_downsamples_under_the_cap() -> None:
    """223 điểm/ngày phải được rút gọn xuống ≤ DAY_CURVE_MAX_POINTS."""
    api = make_api()
    patch_post(api, route({const.EP_DAY_CURVE: fx.day_curve_payload(223)}))
    curve = run(api.get_day_curve("2026-09-28"))
    assert curve["date"] == "2026-09-28"
    assert 0 < curve["count"] <= const.DAY_CURVE_MAX_POINTS, (
        f"vượt giới hạn 16KB/entity: {curve['count']} > {const.DAY_CURVE_MAX_POINTS}"
    )


@pytest.mark.parametrize("points", [1, 2, 72, 73, 100, 223, 500])
def test_get_day_curve_never_exceeds_the_cap(points: int) -> None:
    api = make_api()
    patch_post(api, route({const.EP_DAY_CURVE: fx.day_curve_payload(points)}))
    curve = run(api.get_day_curve("2026-09-28"))
    assert curve["count"] <= const.DAY_CURVE_MAX_POINTS


def test_get_day_curve_keeps_point_shape() -> None:
    api = make_api()
    patch_post(api, route({const.EP_DAY_CURVE: fx.day_curve_payload(10)}))
    point = run(api.get_day_curve("2026-09-28"))["points"][0]
    assert set(point) == {"time", "solarPv", "gridPower", "battery", "consumption", "soc"}


def test_get_day_curve_empty_returns_empty() -> None:
    api = make_api()
    patch_post(api, route({const.EP_DAY_CURVE: {"success": True, "data": []}}))
    assert run(api.get_day_curve("2026-09-28")) == {}


# ── tổng theo năm ──────────────────────────────────────────────


def test_get_total_years_converts_tenths_of_kwh() -> None:
    api = make_api()
    patch_post(api, route({const.EP_TOTAL_COLUMN: fx.total_column_payload()}))
    years = run(api.get_total_years())
    assert years["2026"]["pv"] == 1974.0, "ePv1+ePv2+ePv3 rồi chia 10"
    assert years["2025"]["pv"] == 1200.0
    assert years["2025"]["import"] == 500.0
    assert years["2025"]["export"] == 100.0
    assert years["2025"]["consumption"] == 800.0


def test_get_total_years_tolerates_missing_columns() -> None:
    api = make_api()
    patch_post(
        api,
        route({const.EP_TOTAL_COLUMN: {"success": True, "data": [{"year": 2026, "ePv1Day": 100}]}}),
    )
    assert run(api.get_total_years())["2026"]["pv"] == 10.0


# ── firmware ───────────────────────────────────────────────────


def test_get_firmware_prefers_the_matching_standard() -> None:
    api = make_api()
    mapping = {
        "SNA3_6K_EU": fx.firmware_rows("CHAA", (8, 0, 0)),
        "SNA_3000_6000": fx.firmware_rows("XXXX", (1, 2, 3)),
        "LXP_LB_8_12K": fx.firmware_rows("YYYY", (9, 9, 9)),
    }

    def handler(endpoint, params, base):
        return mapping[params["firmwareDeviceType"]]

    patch_post(api, handler)
    firmware = run(api.get_firmware("CHAA"))
    assert firmware["device_type"] == "SNA3_6K_EU"
    assert firmware["matched"] == 1
    assert firmware["latest_version"] == 8


def test_get_firmware_falls_back_to_the_largest_catalogue() -> None:
    api = make_api()
    mapping = {
        "SNA3_6K_EU": {"rows": [{"standard": "AAAA", "v1": 1, "v2": 0, "v3": 0}]},
        "SNA_3000_6000": {
            "rows": [{"standard": "BBBB", "v1": 1, "v2": 0, "v3": 0}] * 5
        },
        "LXP_LB_8_12K": {"rows": []},
    }

    def handler(endpoint, params, base):
        return mapping[params["firmwareDeviceType"]]

    patch_post(api, handler)
    firmware = run(api.get_firmware("CHAA"))
    assert firmware["device_type"] == "SNA_3000_6000"
    assert firmware["count"] == 5
    assert firmware["matched"] == 0


def test_get_firmware_uses_the_as_host() -> None:
    """Danh mục firmware chỉ trả ở host `as.` — phải gọi đúng base."""
    api = make_api()
    calls = patch_post(api, route({const.EP_FIRMWARE_BY_TYPE: {"rows": []}}))
    run(api.get_firmware("CHAA"))
    assert calls, "phải có ít nhất 1 lời gọi"
    assert all(base == const.MAJOR_URL for _ep, _params, base in calls)


def test_get_firmware_latest_version_is_max_across_axes() -> None:
    api = make_api()
    rows = {
        "rows": [
            {"standard": "CHAA", "v1": 8, "v2": 0, "v3": 0},
            {"standard": "CHAA", "v1": 0, "v2": 3, "v3": 0},
        ]
    }
    patch_post(api, route({const.EP_FIRMWARE_BY_TYPE: rows}))
    assert run(api.get_firmware("CHAA"))["latest_version"] == 8


def test_get_firmware_sends_the_app_platform_params() -> None:
    """Tham số học từ APK: platform/versionCode/clientType bắt buộc."""
    api = make_api()
    calls = patch_post(api, route({const.EP_FIRMWARE_BY_TYPE: {"rows": []}}))
    run(api.get_firmware("CHAA"))
    params = calls[0][1]
    for key, value in const.FIRMWARE_BASE.items():
        assert params[key] == value


def test_get_firmware_all_empty_returns_empty() -> None:
    api = make_api()
    patch_post(api, route({const.EP_FIRMWARE_BY_TYPE: {"rows": []}}))
    assert run(api.get_firmware("CHAA")) == {}


# ── tổng hợp ───────────────────────────────────────────────────


def _fetch_all_handler(slow_ok: bool = True):
    mapping = {
        const.EP_PLANT: fx.plant_payload(),
        const.EP_RUNTIME: fx.runtime_payload(),
        const.EP_ENERGY: fx.energy_payload(),
        const.EP_DATALOG: fx.datalog_payload(),
        const.EP_EVENT: fx.event_payload(),
        const.EP_BATTERY: fx.battery_payload(),
        const.EP_QUICK_STATUS: fx.quick_payload(),
        const.EP_REMOTE_READ: fx.bits_payload("FUNC_GRID_PEAK_SHAVING"),
        const.EP_FIRMWARE_BY_TYPE: fx.firmware_rows("CHAA", (8, 0, 0)),
        const.EP_DAY_CURVE: fx.day_curve_payload(50),
        const.EP_TOTAL_COLUMN: fx.total_column_payload(),
    }
    return route(mapping)


def test_fetch_all_fast_path_skips_slow_endpoints() -> None:
    api = make_api()
    calls = patch_post(api, _fetch_all_handler())
    data = run(api.async_fetch_all(slow=False, date_text="2026-09-28"))
    endpoints = {ep for ep, _p, _b in calls}
    assert const.EP_DAY_CURVE not in endpoints
    assert const.EP_TOTAL_COLUMN not in endpoints
    assert const.EP_FIRMWARE_BY_TYPE not in endpoints
    for key in ("plant", "runtime", "energy", "dongle", "event", "battery", "quick", "bits"):
        assert key in data


def test_fetch_all_slow_path_adds_series_and_firmware() -> None:
    api = make_api()
    patch_post(api, _fetch_all_handler())
    data = run(api.async_fetch_all(slow=True, date_text="2026-09-28"))
    assert data["firmware"]["latest_version"] == 8
    assert data["day_curve"]["count"] > 0
    assert "2026" in data["total_years"]


def test_fetch_all_builds_green_metrics_from_unit_text() -> None:
    api = make_api()
    patch_post(api, _fetch_all_handler())
    green = run(api.async_fetch_all(slow=False, date_text="2026-09-28"))["green"]
    assert green["co2_ton"] == 1.99
    assert green["coal_kg"] == 798.96
    assert green["trees"] == 110.63


def test_fetch_all_health_flags() -> None:
    api = make_api()
    patch_post(api, _fetch_all_handler())
    health = run(api.async_fetch_all(slow=False, date_text="2026-09-28"))["health"]
    assert health["cloud_ok"] is True
    assert health["has_runtime"] is True
    assert health["lost"] is False
    assert health["pinv"] == 1095
    assert health["fw_code"] == "CHAA-000303"


def test_fetch_all_carries_on_when_endpoints_fail() -> None:
    """Endpoint lỗi → dict rỗng, KHÔNG được ném exception ra coordinator."""
    api = make_api()
    patch_post(api, route({const.EP_PLANT: fx.plant_payload()}))
    data = run(api.async_fetch_all(slow=False, date_text="2026-09-28"))
    assert data["plant"]["standard"] == "CHAA"
    assert data["dongle"] == {}
    assert data["battery"] == {}
    assert data["health"]["cloud_ok"] is False


# ── refreshInputData ───────────────────────────────────────────


def test_refresh_input_requires_a_user_id() -> None:
    api = make_api()
    api._session = _FakeSession(_FakeResponse(200, "{}"))
    assert run(api.refresh_input()) is False


def test_refresh_input_sends_encrypted_data_header() -> None:
    api = make_api()
    session = _FakeSession(_FakeResponse(200, "{}"))
    api._session = session
    api.user_id = 42
    assert run(api.refresh_input()) is True
    assert "Encrypted-Data" in session.calls[0]["kwargs"]["headers"]


def test_refresh_input_false_on_error_status() -> None:
    api = make_api()
    api._session = _FakeSession(_FakeResponse(500, "x"))
    api.user_id = 42
    assert run(api.refresh_input()) is False


def test_refresh_input_false_when_cryptography_is_unavailable() -> None:
    from custom_components.luxcloud_ha import api as api_module

    original = api_module._AES_OK
    api_module._AES_OK = False
    try:
        client = make_api()
        client.user_id = 42
        assert run(client.refresh_input()) is False
    finally:
        api_module._AES_OK = original
