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
