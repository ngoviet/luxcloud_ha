"""Integration metadata, verified through Home Assistant's own consumers.

These assertions deliberately go through HA rather than reading our files:
`async_get_integration` makes HA parse and accept `manifest.json` (so a malformed
or mis-keyed manifest fails here), and `async_get_translations` makes HA resolve
the strings the config flow renders. Reading the JSON ourselves would only prove
the file contains text, not that HA accepts it.
"""
from __future__ import annotations

import pytest
from homeassistant import loader as ha_loader
from homeassistant.helpers.translation import async_get_translations

from custom_components.luxcloud_ha.const import DOMAIN

# Error keys the config flow can return — each one is also provoked for real in
# test_config_flow.py, so this table cannot drift away from actual behaviour.
CONFIG_ERROR_KEYS = ("invalid_auth", "cannot_connect", "no_device", "unknown")


async def test_ha_loader_accepts_the_manifest(hass) -> None:
    integration = await ha_loader.async_get_integration(hass, DOMAIN)

    assert integration.domain == DOMAIN
    assert integration.name
    assert integration.config_flow is True
    assert integration.dependencies == ["http"]
    assert integration.requirements == [], "integration phải không cần thư viện ngoài"
    assert integration.iot_class == "cloud_polling"
    assert integration.integration_type == "hub"


async def test_manifest_points_at_this_repository(hass) -> None:
    """Sai slug repo ⇒ nút 'Add to HACS' và issue tracker hỏng."""
    integration = await ha_loader.async_get_integration(hass, DOMAIN)

    assert integration.documentation == "https://github.com/ngoviet/luxcloud_ha"
    assert integration.issue_tracker == "https://github.com/ngoviet/luxcloud_ha/issues"


async def test_ha_can_load_our_config_strings(hass) -> None:
    strings = await async_get_translations(hass, "en", "config", {DOMAIN})
    assert strings, "HA không đọc được chuỗi cấu hình nào"


@pytest.mark.parametrize("error_key", CONFIG_ERROR_KEYS)
async def test_every_config_error_key_resolves_in_translations(hass, error_key: str) -> None:
    """Mỗi lỗi config flow trả về phải có chuỗi cho HA hiển thị."""
    strings = await async_get_translations(hass, "en", "config", {DOMAIN})
    matching = [key for key in strings if key.endswith(f"error.{error_key}")]
    assert matching, f"thiếu chuỗi dịch cho lỗi '{error_key}' (có: {sorted(strings)})"


async def test_ha_exposes_the_service_translations(hass) -> None:
    strings = await async_get_translations(hass, "en", "services", {DOMAIN})
    assert any(key.endswith("set_bit.name") for key in strings), sorted(strings)
    assert any(key.endswith("set_bit.fields.function.name") for key in strings), sorted(strings)
    assert any(key.endswith("set_bit.fields.enable.name") for key in strings), sorted(strings)


def _field_names(schema) -> set[str]:
    """Tên field từ schema THẬT của flow (không hardcode)."""
    names = set()
    for key in schema.schema:
        name = getattr(key, "schema", key)
        if isinstance(name, str):
            names.add(name)
    return names


async def test_every_config_field_is_labelled_and_described(hass) -> None:
    """Rule bronze `config-flow`: field phải có cả nhãn và `data_description`.

    Lấy field từ schema thật, đối chiếu với chuỗi mà HA thật sự load — nên thêm
    field mới mà quên mô tả là test đỏ, không cần ai nhớ.
    """
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    fields = _field_names(result["data_schema"])
    assert fields == {"account", "password", "serial", "region", "scan_interval"}

    strings = await async_get_translations(hass, "en", "config", {DOMAIN})
    for field in fields:
        assert any(key.endswith(f"data.{field}") for key in strings), f"thiếu nhãn: {field}"
        assert any(key.endswith(f"data_description.{field}") for key in strings), (
            f"thiếu data_description cho '{field}' — rule bronze 'config-flow'"
        )


async def test_reauth_fields_are_labelled_and_described(hass, patched_api) -> None:
    from tests.conftest import setup_luxcloud

    entry = await setup_luxcloud(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": entry.entry_id}
    )
    fields = _field_names(result["data_schema"])
    assert fields == {"account", "password"}

    strings = await async_get_translations(hass, "en", "config", {DOMAIN})
    for field in fields:
        assert any(key.endswith(f"data_description.{field}") for key in strings), field


async def test_every_options_field_is_labelled_and_described(hass, patched_api) -> None:
    """Chuỗi của options flow nằm ở category `options`, không phải `config`."""
    from tests.conftest import setup_luxcloud

    entry = await setup_luxcloud(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fields = _field_names(result["data_schema"])
    assert fields == {"scan_interval", "enable_series", "enable_firmware"}

    strings = await async_get_translations(hass, "en", "options", {DOMAIN})
    assert strings, "HA không đọc được chuỗi tuỳ chọn nào"
    for field in fields:
        assert any(key.endswith(f"data.{field}") for key in strings), f"thiếu nhãn: {field}"
        assert any(key.endswith(f"data_description.{field}") for key in strings), (
            f"thiếu data_description cho tuỳ chọn '{field}'"
        )
