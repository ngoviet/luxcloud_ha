"""DataUpdateCoordinator cho LuxCloud."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import LuxCloudApi, LuxCloudApiError, LuxCloudAuthError
from .const import (
    CONF_ENABLE_FIRMWARE,
    CONF_ENABLE_SERIES,
    DOMAIN,
    SLOW_EVERY,
)

_LOGGER = logging.getLogger(__name__)

SLOW_KEYS = ("firmware", "day_curve", "total_years")


class LuxCloudCoordinator(DataUpdateCoordinator[dict]):
    """Poll cloud mỗi `scan_interval`; dữ liệu 'chậm' (firmware/chuỗi) lấy mỗi SLOW_EVERY lần."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: LuxCloudApi,
        entry: ConfigEntry,
        update_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.api = api
        self._tick = 0
        self._cache: dict = {}

    async def _async_update_data(self) -> dict:
        self._tick += 1
        want_slow = bool(
            self.config_entry.options.get(CONF_ENABLE_SERIES, True)
            or self.config_entry.options.get(CONF_ENABLE_FIRMWARE, True)
        )
        slow = self._tick == 1 or (want_slow and self._tick % SLOW_EVERY == 0)
        try:
            data = await self.api.async_fetch_all(
                slow=slow, date_text=dt_util.now().strftime("%Y-%m-%d")
            )
        except LuxCloudAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LuxCloudApiError as err:
            raise UpdateFailed(str(err)) from err

        if not data.get("plant") and not data.get("runtime"):
            raise UpdateFailed("cloud không trả dữ liệu (plant/runtime rỗng)")

        # giữ dữ liệu 'chậm' giữa các tick
        for key in SLOW_KEYS:
            if data.get(key):
                self._cache[key] = data[key]
            elif self._cache.get(key):
                data[key] = self._cache[key]

        # khoá chậm có thể bị tắt trong options
        if not self.config_entry.options.get(CONF_ENABLE_FIRMWARE, True):
            data.pop("firmware", None)
        if not self.config_entry.options.get(CONF_ENABLE_SERIES, True):
            data.pop("day_curve", None)
            data.pop("total_years", None)
        return data
