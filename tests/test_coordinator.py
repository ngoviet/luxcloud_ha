"""Test coordinator: nhịp poll, cache khoá 'chậm', và ánh xạ lỗi sang HA."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxcloud_ha.api import LuxCloudApiError, LuxCloudAuthError
from custom_components.luxcloud_ha.const import (
    CONF_ENABLE_FIRMWARE,
    CONF_ENABLE_SERIES,
    DOMAIN,
)
from custom_components.luxcloud_ha.coordinator import (
    SLOW_EVERY,
    SLOW_KEYS,
    LuxCloudCoordinator,
)


class _StubApi:
    """API giả: ghi lại tham số `slow` và trả dữ liệu theo kịch bản."""

    def __init__(self, responses: list[dict] | None = None, error: Exception | None = None):
        self.responses = responses or []
        self.error = error
        self.calls: list[bool] = []

    async def async_fetch_all(self, slow: bool, date_text: str) -> dict:
        self.calls.append(slow)
        if self.error is not None:
            raise self.error
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return dict(self.responses[index]) if self.responses else {}


def _entry(**options) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={"serial": "61204F0266"},
        options={
            CONF_ENABLE_SERIES: options.get(CONF_ENABLE_SERIES, True),
            CONF_ENABLE_FIRMWARE: options.get(CONF_ENABLE_FIRMWARE, True),
        },
    )


def _coordinator(hass, api, entry) -> LuxCloudCoordinator:
    entry.add_to_hass(hass)
    return LuxCloudCoordinator(hass, api, entry, 300)


BASE_DATA = {"plant": {"standard": "CHAA"}, "runtime": {"pinv": 1}}


async def test_first_poll_always_fetches_slow_data(hass) -> None:
    """Tick 1 phải lấy firmware/chuỗi ngay, không đợi 6 nhịp."""
    api = _StubApi([BASE_DATA])
    coordinator = _coordinator(hass, api, _entry())
    await coordinator._async_update_data()
    assert api.calls == [True]


async def test_fast_polls_skip_slow_data(hass) -> None:
    api = _StubApi([{**BASE_DATA, "firmware": {"latest_version": 8}}])
    coordinator = _coordinator(hass, api, _entry())
    await coordinator._async_update_data()  # tick 1 → slow
    await coordinator._async_update_data()  # tick 2 → fast
    assert api.calls == [True, False]


async def test_slow_refresh_repeats_every_slow_every_ticks(hass) -> None:
    api = _StubApi([BASE_DATA])
    coordinator = _coordinator(hass, api, _entry())
    for _ in range(SLOW_EVERY):
        await coordinator._async_update_data()
    assert api.calls == [True] + [False] * (SLOW_EVERY - 2) + [True]


async def test_slow_data_is_cached_between_ticks(hass) -> None:
    """Tick nhanh không trả firmware → entity phải giữ giá trị cũ, không về unknown."""
    api = _StubApi(
        [
            {**BASE_DATA, "firmware": {"latest_version": 8}},
            dict(BASE_DATA),
        ]
    )
    coordinator = _coordinator(hass, api, _entry())
    await coordinator._async_update_data()
    data = await coordinator._async_update_data()
    assert data["firmware"] == {"latest_version": 8}


async def test_disabling_firmware_removes_the_key(hass) -> None:
    api = _StubApi([{**BASE_DATA, "firmware": {"latest_version": 8}}])
    coordinator = _coordinator(hass, api, _entry(**{CONF_ENABLE_FIRMWARE: False}))
    data = await coordinator._async_update_data()
    assert "firmware" not in data


async def test_disabling_series_removes_curve_and_totals(hass) -> None:
    api = _StubApi(
        [{**BASE_DATA, "day_curve": {"count": 5}, "total_years": {"2026": {"pv": 1.0}}}]
    )
    coordinator = _coordinator(hass, api, _entry(**{CONF_ENABLE_SERIES: False}))
    data = await coordinator._async_update_data()
    assert "day_curve" not in data
    assert "total_years" not in data


async def test_both_disabled_means_no_slow_ticks_after_the_first(hass) -> None:
    api = _StubApi([BASE_DATA])
    coordinator = _coordinator(
        hass, api, _entry(**{CONF_ENABLE_SERIES: False, CONF_ENABLE_FIRMWARE: False})
    )
    for _ in range(SLOW_EVERY):
        await coordinator._async_update_data()
    assert api.calls == [True] + [False] * (SLOW_EVERY - 1)


async def test_empty_cloud_response_raises_update_failed(hass) -> None:
    from homeassistant.helpers.update_coordinator import UpdateFailed

    api = _StubApi([{}])
    coordinator = _coordinator(hass, api, _entry())
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_plant_or_runtime_alone_is_enough(hass) -> None:
    api = _StubApi([{"plant": {}, "runtime": {"pinv": 5}}])
    coordinator = _coordinator(hass, api, _entry())
    assert (await coordinator._async_update_data())["runtime"] == {"pinv": 5}


async def test_auth_error_becomes_config_entry_auth_failed(hass) -> None:
    from homeassistant.exceptions import ConfigEntryAuthFailed

    api = _StubApi(error=LuxCloudAuthError("sai mật khẩu"))
    coordinator = _coordinator(hass, api, _entry())
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_api_error_becomes_update_failed(hass) -> None:
    from homeassistant.helpers.update_coordinator import UpdateFailed

    api = _StubApi(error=LuxCloudApiError("mạng lỗi"))
    coordinator = _coordinator(hass, api, _entry())
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


def test_slow_keys_are_exactly_the_cached_ones() -> None:
    """SLOW_KEYS phải khớp 3 khoá mà api.async_fetch_all bơm thêm khi slow=True."""
    assert set(SLOW_KEYS) == {"firmware", "day_curve", "total_years"}


def test_update_interval_is_applied_to_the_coordinator(hass) -> None:
    from datetime import timedelta

    coordinator = _coordinator(hass, _StubApi([]), _entry())
    assert coordinator.update_interval == timedelta(seconds=300)
