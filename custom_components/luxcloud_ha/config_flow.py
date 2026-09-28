"""Config flow + Options flow cho LuxCloud."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LuxCloudApi, LuxCloudApiError, LuxCloudAuthError
from .const import (
    CONF_ACCOUNT,
    CONF_ENABLE_FIRMWARE,
    CONF_ENABLE_SERIES,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REGIONS,
)

_LOGGER = logging.getLogger(__name__)


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> str | None:
    """Trả về error key hoặc None nếu OK."""
    serial = str(data[CONF_SERIAL]).strip().upper()
    api = LuxCloudApi(
        async_get_clientsession(hass),
        REGIONS.get(str(data.get(CONF_REGION, DEFAULT_REGION)).lower(), REGIONS[DEFAULT_REGION]),
        str(data[CONF_ACCOUNT]).strip(),
        str(data[CONF_PASSWORD]),
        serial,
    )
    try:
        await api.login()
    except LuxCloudAuthError:
        return "invalid_auth"
    except LuxCloudApiError:
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        _LOGGER.exception("luxcloud: lỗi không xác định khi đăng nhập")
        return "unknown"
    try:
        plant = await api.get_plant()
    except Exception:  # noqa: BLE001
        return "cannot_connect"
    if not plant:
        return "no_device"
    return None


class LuxCloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Nhập tài khoản cloud + serial inverter."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            serial = str(user_input[CONF_SERIAL]).strip().upper()
            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()
            err = await _validate(self.hass, user_input)
            if err:
                errors["base"] = err
            else:
                data = dict(user_input)
                data[CONF_SERIAL] = serial
                return self.async_create_entry(
                    title=f"LuxCloud {serial}",
                    data=data,
                    options={
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_ENABLE_SERIES: True,
                        CONF_ENABLE_FIRMWARE: True,
                    },
                )
        return self.async_show_form(step_id="user", data_schema=self._schema(user_input), errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Sai mật khẩu → yêu cầu nhập lại (giữ serial)."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        entry = getattr(self, "_reauth_entry", None)
        if user_input is not None and entry is not None:
            merged = {**entry.data, **user_input}
            err = await _validate(self.hass, merged)
            if err:
                errors["base"] = err
            else:
                self.hass.config_entries.async_update_entry(entry, data=merged)
                return self.async_abort(reason="reauth_successful")
        schema = vol.Schema(
            {
                vol.Required(CONF_ACCOUNT, default=(entry.data.get(CONF_ACCOUNT) if entry else "")): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)

    @staticmethod
    def _schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
        ui = user_input or {}
        return vol.Schema(
            {
                vol.Required(CONF_ACCOUNT, default=ui.get(CONF_ACCOUNT, "")): str,
                vol.Required(CONF_PASSWORD, default=ui.get(CONF_PASSWORD, "")): str,
                vol.Required(CONF_SERIAL, default=ui.get(CONF_SERIAL, "")): str,
                vol.Optional(CONF_REGION, default=ui.get(CONF_REGION, DEFAULT_REGION)): vol.In(
                    sorted(REGIONS)
                ),
                vol.Optional(CONF_SCAN_INTERVAL, default=ui.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(
                    int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return LuxCloudOptionsFlow()


class LuxCloudOptionsFlow(OptionsFlow):
    """Chu kỳ poll + bật/tắt dữ liệu 'chậm'."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                vol.Optional(
                    CONF_ENABLE_SERIES, default=opts.get(CONF_ENABLE_SERIES, True)
                ): bool,
                vol.Optional(
                    CONF_ENABLE_FIRMWARE, default=opts.get(CONF_ENABLE_FIRMWARE, True)
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
