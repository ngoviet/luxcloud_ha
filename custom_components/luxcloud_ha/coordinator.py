"""DataUpdateCoordinator cho LuxCloud."""
from __future__ import annotations

import logging
from collections.abc import Awaitable
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from . import energy
from .api import LuxCloudApi, LuxCloudApiError, LuxCloudAuthError
from .const import (
    CONF_BILLING_DAY,
    CONF_ENABLE_FIRMWARE,
    CONF_ENABLE_SERIES,
    DEFAULT_BILLING_DAY,
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
        billing_day = int(options.get(CONF_BILLING_DAY, DEFAULT_BILLING_DAY))
        now = dt_util.now()
        today = now.strftime("%Y-%m-%d")
        try:
            data = await self._async_fetch(slow, want_firmware, want_series, today, billing_day)
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

        # Kỳ hoá đơn / năm / hôm qua: phần nào lần này lỗi thì giữ bản cũ CÙNG kỳ.
        data["periods"] = energy.merge_periods(
            data.get("periods"), self._cache.get("periods"), now.date(), billing_day
        )
        self._cache["periods"] = data["periods"]

        # Chuỗi "hôm nay" chỉ lấy ở nhịp chậm: qua nửa đêm, bản cache là của
        # HÔM QUA nhưng vẫn được trình bày là hôm nay cho tới nhịp chậm kế tiếp
        # (tới ~30 phút; lâu hơn nếu cloud chưa có điểm nào của ngày mới).
        if (data.get("day_curve") or {}).get("date") not in (None, today):
            data.pop("day_curve")
            self._cache.pop("day_curve", None)

        # khoá chậm có thể bị tắt trong options
        if not want_firmware:
            data.pop("firmware", None)
        if not want_series:
            data.pop("day_curve", None)
            data.pop("total_years", None)
        return data

    async def async_write(self, write: Awaitable[bool], what: str) -> bool:
        """Chạy một lệnh GHI của api; trả kết quả cloud (`success`).

        Đường ghi tự đăng nhập lại khi phiên hết hạn, nên có thể ném lỗi của
        `login()`. Nếu để exception thô của api lọt ra thì UI chỉ hiện "Unknown
        error" — nên đổi sang `HomeAssistantError` có nghĩa, và sai mật khẩu thì mở
        luôn reauth flow như khi poll.
        """
        try:
            return await write
        except LuxCloudAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                f"LuxCloud từ chối đăng nhập khi ghi {what} — cần đăng nhập lại: {err}"
            ) from err
        except LuxCloudApiError as err:
            raise HomeAssistantError(f"LuxCloud không phản hồi khi ghi {what}: {err}") from err

    async def _async_fetch(
        self, slow: bool, firmware: bool, series: bool, date_text: str, billing_day: int
    ) -> dict:
        """Một lần poll; phiên hết hạn thì đăng nhập lại rồi thử ĐÚNG một lần nữa.

        Phiên JSESSIONID hết hạn thì cloud trả trang login/`success=false` → mọi
        endpoint ra rỗng. Một số trường hợp có thể là HTTP 401 — cũng chỉ nghĩa
        là PHIÊN hỏng, chưa chắc mật khẩu sai, nên cũng đăng nhập lại trước.
        Chỉ khi chính `login()` bị từ chối mới là sai mật khẩu thật (→ reauth).
        """
        async def fetch() -> dict:
            return await self.api.async_fetch_all(
                slow=slow,
                date_text=date_text,
                firmware=firmware,
                series=series,
                billing_day=billing_day,
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
