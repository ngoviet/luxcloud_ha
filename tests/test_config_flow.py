"""Test config flow + options flow: validate, lỗi, unique_id, reauth."""
from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxcloud_ha import const
from custom_components.luxcloud_ha.api import LuxCloudApiError, LuxCloudAuthError
from custom_components.luxcloud_ha.config_flow import LuxCloudConfigFlow

USER_INPUT = {
    const.CONF_ACCOUNT: "u@example.com",
    const.CONF_PASSWORD: "pw",
    const.CONF_SERIAL: "61204f0266",
    const.CONF_REGION: "vn",
}


class _FakeApi:
    """API giả điều khiển được hành vi login/get_plant."""

    login_error: Exception | None = None
    plant: dict | None = None
    instances: list["_FakeApi"] = []

    def __init__(self, session, base_url, account, password, serial) -> None:
        self.base_url = base_url
        self.account = account
        self.password = password
        self.serial = serial.upper()
        self.plant_id = 1
        _FakeApi.instances.append(self)

    async def login(self) -> bool:
        if _FakeApi.login_error is not None:
            raise _FakeApi.login_error
        return True

    async def get_plant(self) -> dict:
        return _FakeApi.plant if _FakeApi.plant is not None else {"plant_id": 1}


@pytest.fixture
def flow_api(monkeypatch):
    _FakeApi.instances.clear()
    _FakeApi.login_error = None
    _FakeApi.plant = None
    monkeypatch.setattr("custom_components.luxcloud_ha.config_flow.LuxCloudApi", _FakeApi)
    yield _FakeApi
    _FakeApi.login_error = None
    _FakeApi.plant = None


# ── Schema ─────────────────────────────────────────────────────


def test_schema_applies_defaults() -> None:
    result = LuxCloudConfigFlow._schema()(
        {
            const.CONF_ACCOUNT: "a",
            const.CONF_PASSWORD: "b",
            const.CONF_SERIAL: "c",
        }
    )
    assert result[const.CONF_REGION] == const.DEFAULT_REGION
    assert result[const.CONF_SCAN_INTERVAL] == const.DEFAULT_SCAN_INTERVAL


def test_schema_rejects_an_unknown_region() -> None:
    with pytest.raises(vol.Invalid):
        LuxCloudConfigFlow._schema()({**USER_INPUT, const.CONF_REGION: "mars"})


@pytest.mark.parametrize(
    "interval", [const.MIN_SCAN_INTERVAL - 1, const.MAX_SCAN_INTERVAL + 1, 0, -5]
)
def test_schema_rejects_scan_interval_out_of_range(interval: int) -> None:
    with pytest.raises(vol.Invalid):
        LuxCloudConfigFlow._schema()({**USER_INPUT, const.CONF_SCAN_INTERVAL: interval})


@pytest.mark.parametrize("interval", [const.MIN_SCAN_INTERVAL, const.MAX_SCAN_INTERVAL])
def test_schema_accepts_the_bounds(interval: int) -> None:
    result = LuxCloudConfigFlow._schema()({**USER_INPUT, const.CONF_SCAN_INTERVAL: interval})
    assert result[const.CONF_SCAN_INTERVAL] == interval


def test_schema_accepts_every_region() -> None:
    for region in const.REGIONS:
        result = LuxCloudConfigFlow._schema()({**USER_INPUT, const.CONF_REGION: region})
        assert result[const.CONF_REGION] == region


# ── Flow ───────────────────────────────────────────────────────


async def test_user_flow_shows_a_form_first(hass, flow_api) -> None:
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_flow_creates_the_entry(hass, flow_api) -> None:
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LuxCloud 61204F0266"
    assert result["data"][const.CONF_SERIAL] == "61204F0266", "serial phải được upper-case"
    # options mặc định được set khi tạo entry
    assert result["options"][const.CONF_SCAN_INTERVAL] == const.DEFAULT_SCAN_INTERVAL
    assert result["options"][const.CONF_ENABLE_SERIES] is True
    assert result["options"][const.CONF_ENABLE_FIRMWARE] is True


async def test_serial_is_normalised_before_login(hass, flow_api) -> None:
    """Người dùng gõ chữ thường vẫn phải đăng nhập bằng serial đã upper-case."""
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, const.CONF_SERIAL: "  61204f0266  "}
    )
    assert flow_api.instances[-1].serial == "61204F0266"


async def test_wrong_password_reports_invalid_auth(hass, flow_api) -> None:
    flow_api.login_error = LuxCloudAuthError("sai mật khẩu")
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_network_error_reports_cannot_connect(hass, flow_api) -> None:
    flow_api.login_error = LuxCloudApiError("mạng lỗi")
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["errors"] == {"base": "cannot_connect"}


async def test_unexpected_error_reports_unknown(hass, flow_api) -> None:
    flow_api.login_error = RuntimeError("bùm")
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["errors"] == {"base": "unknown"}


async def test_unknown_serial_reports_no_device(hass, flow_api) -> None:
    """Login OK nhưng không có plant → serial sai."""
    flow_api.plant = {}
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["errors"] == {"base": "no_device"}


async def test_adding_the_same_serial_twice_aborts(hass, flow_api) -> None:
    MockConfigEntry(domain=const.DOMAIN, unique_id="61204F0266").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_region_falls_back_to_default_for_unknown_value(hass, flow_api) -> None:
    """`_validate` dùng REGIONS.get(..., default) — không được KeyError."""
    from custom_components.luxcloud_ha.config_flow import _validate

    err = await _validate(
        hass,
        {
            const.CONF_ACCOUNT: "a",
            const.CONF_PASSWORD: "b",
            const.CONF_SERIAL: "s",
            const.CONF_REGION: "mars",
        },
    )
    assert err is None
    assert flow_api.instances[-1].base_url == const.REGIONS[const.DEFAULT_REGION]


# ── Reauth ─────────────────────────────────────────────────────


async def test_reauth_flow_updates_the_password(hass, flow_api) -> None:
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        unique_id="61204F0266",
        data={**USER_INPUT, const.CONF_SERIAL: "61204F0266"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        const.DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
    )
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {const.CONF_ACCOUNT: "u@example.com", const.CONF_PASSWORD: "new-pw"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[const.CONF_PASSWORD] == "new-pw"
    assert entry.data[const.CONF_SERIAL] == "61204F0266", "reauth phải giữ serial"
