"""DataUpdateCoordinator cho LuxCloud."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)
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


class LuxCloudCoordinator(TimestampDataUpdateCoordinator[dict]):
    """Poll cloud mỗi `scan_interval`; dữ liệu 'chậm' (firmware/chuỗi) lấy mỗi SLOW_EVERY lần.

    Kế thừa `TimestampDataUpdateCoordinator` (không phải `DataUpdateCoordinator`) vì
    nó ghi lại `last_update_success_time` — thứ cần để trả lời "dữ liệu này cũ bao lâu"
    trong diagnostics mà không phải tự thêm state.
    """

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
        # Đếm số lần poll HỎNG LIÊN TIẾP. HA không có sẵn bộ đếm này, mà nó là
        # thứ cần nhất khi cloud chập chờn: 1 lần lỗi là bình thường, 20 lần liên
        # tiếp là sự cố thật. Đưa vào diagnostics để khỏi phải mò log.
        self.failed_updates = 0

    async def _async_update_data(self) -> dict:
        self._tick += 1
        options = self.config_entry.options
        want_firmware = bool(options.get(CONF_ENABLE_FIRMWARE, True))
        want_series = bool(options.get(CONF_ENABLE_SERIES, True))
        slow = (want_firmware or want_series) and (
            self._tick == 1 or self._tick % SLOW_EVERY == 0
        )
        try:
            data = await self._async_fetch(slow, want_firmware, want_series)
        except LuxCloudAuthError as err:
            self.failed_updates += 1
            raise ConfigEntryAuthFailed(str(err)) from err
        except LuxCloudApiError as err:
            self.failed_updates += 1
            raise UpdateFailed(str(err)) from err

        if not _has_data(data):
            self.failed_updates += 1
            raise UpdateFailed("cloud không trả dữ liệu (plant/runtime rỗng)")

        self.failed_updates = 0

        # giữ dữ liệu 'chậm' giữa các tick
        for key in SLOW_KEYS:
            if data.get(key):
                self._cache[key] = data[key]
            elif self._cache.get(key):
                data[key] = self._cache[key]

        # khoá chậm có thể bị tắt trong options
        if not want_firmware:
            data.pop("firmware", None)
        if not want_series:
            data.pop("day_curve", None)
            data.pop("total_years", None)
        return data

    async def _async_fetch(self, slow: bool, firmware: bool, series: bool) -> dict:
        """Một lần poll; phiên hết hạn thì đăng nhập lại rồi thử ĐÚNG một lần nữa.

        Phiên JSESSIONID hết hạn thì cloud trả trang login/`success=false` → mọi
        endpoint ra rỗng. Một số trường hợp có thể là HTTP 401 — cũng chỉ nghĩa
        là PHIÊN hỏng, chưa chắc mật khẩu sai, nên cũng đăng nhập lại trước.
        Chỉ khi chính `login()` bị từ chối mới là sai mật khẩu thật (→ reauth).
        """
        date_text = dt_util.now().strftime("%Y-%m-%d")

        async def fetch() -> dict:
            return await self.api.async_fetch_all(
                slow=slow, date_text=date_text, firmware=firmware, series=series
            )

        try:
            data = await fetch()
        except LuxCloudAuthError:
            data = None
        if data is not None and _has_data(data):
            return data

        _LOGGER.debug("luxcloud: phiên cloud có vẻ đã hết hạn — đăng nhập lại")
        await self.api.login()  # LuxCloudAuthError ở đây = sai mật khẩu thật
        try:
            return await fetch()
        except LuxCloudAuthError as err:
            # Vừa đăng nhập ĐƯỢC mà vẫn 401 → lỗi phía cloud, không phải mật khẩu.
            raise LuxCloudApiError(f"cloud từ chối ngay sau khi đăng nhập lại: {err}") from err


def _has_data(data: dict) -> bool:
    return bool(data.get("plant") or data.get("runtime"))
