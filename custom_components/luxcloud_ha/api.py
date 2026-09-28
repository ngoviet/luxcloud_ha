"""Client gọi LuxPower Cloud API (WManage) — bất đồng bộ, dùng aiohttp của HA.

Kiến thức endpoint/field lấy từ APK LuxCloud 4.9.8 (jadx) và đã đo thật.
Đăng nhập: POST /api/login (form-urlencoded) → cookie JSESSIONID.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    AES_KEY,
    CONFIG_BIT_BLOCK,
    CONFIG_BIT_KEYS,
    DAY_CURVE_MAX_POINTS,
    EP_BATTERY,
    EP_DATALOG,
    EP_DAY_CURVE,
    EP_ENERGY,
    EP_EVENT,
    EP_FIRMWARE_BY_TYPE,
    EP_LOGIN,
    EP_PLANT,
    EP_QUICK_STATUS,
    EP_REFRESH,
    EP_REMOTE_READ,
    EP_RUNTIME,
    EP_TOTAL_COLUMN,
    FIRMWARE_BASE,
    FIRMWARE_TYPES,
    MAJOR_URL,
)

_LOGGER = logging.getLogger(__name__)

try:  # HA luôn có `cryptography`; nếu thiếu thì bỏ qua refreshInputData
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    _AES_OK = True
except Exception:  # noqa: BLE001
    _AES_OK = False


class LuxCloudAuthError(Exception):
    """Sai tài khoản/mật khẩu."""


class LuxCloudApiError(Exception):
    """Lỗi mạng/API."""


def _aes_encrypt(plaintext: str) -> str:
    data = plaintext.encode()
    pad = 16 - (len(data) % 16)
    data += bytes([pad] * pad)
    encryptor = Cipher(algorithms.AES(AES_KEY), modes.ECB()).encryptor()
    return base64.b64encode(encryptor.update(data) + encryptor.finalize()).decode()


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _f(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _num_text(txt: Any) -> float | None:
    """'1.96 Ton' -> 1.96 ; '--' -> None"""
    try:
        return float(str(txt).split()[0])
    except (ValueError, IndexError, AttributeError):
        return None


class LuxCloudApi:
    """Bọc các lời gọi cloud cần cho Phase 1 (chỉ đọc)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        account: str,
        password: str,
        serial: str,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._account = account
        self._password = password
        self.serial = serial.upper()
        self.user_id: int | None = None
        self.plant_id: int | None = None

    # ── HTTP ───────────────────────────────────────────────────
    async def _post(self, endpoint: str, params: dict | None, base: str | None = None) -> dict | None:
        url = f"{base or self._base_url}{endpoint}"
        data = aiohttp.FormData({k: str(v) for k, v in (params or {}).items()})
        try:
            async with self._session.post(
                url, data=data, timeout=aiohttp.ClientTimeout(total=25)
            ) as resp:
                if resp.status == 401:
                    raise LuxCloudAuthError("HTTP 401")
                if resp.status != 200:
                    _LOGGER.debug("luxcloud %s -> HTTP %s", endpoint, resp.status)
                    return None
                text = await resp.text()
        except LuxCloudAuthError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("luxcloud %s lỗi mạng: %s", endpoint, err)
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    async def login(self) -> bool:
        payload = await self._post(
            EP_LOGIN,
            {"account": self._account, "password": self._password, "language": "ENGLISH"},
        )
        if payload is None:
            raise LuxCloudApiError("login: không có phản hồi")
        if not payload.get("success"):
            raise LuxCloudAuthError(str(payload.get("msg", "login failed")))
        self.user_id = _i(payload.get("userId"), 0) or None
        return True

    async def refresh_input(self) -> bool:
        """Ép cloud poll dongle (giống app kéo-refresh). Cần header Encrypted-Data."""
        if not (_AES_OK and self.user_id):
            return False
        token = _aes_encrypt(f"{int(time.time() * 1000)}&{self.user_id}")
        url = f"{self._base_url}{EP_REFRESH}"
        try:
            async with self._session.post(
                url,
                data=aiohttp.FormData({"serialNum": self.serial}),
                headers={"Encrypted-Data": token},
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                return resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    # ── Dữ liệu ────────────────────────────────────────────────
    async def get_runtime(self) -> dict:
        r = await self._post(EP_RUNTIME, {"serialNum": self.serial}) or {}
        return r if r.get("success") else {}

    async def get_energy(self) -> dict:
        r = await self._post(EP_ENERGY, {"serialNum": self.serial}) or {}
        return r if r.get("success") else {}

    async def get_plant(self) -> dict:
        r = await self._post(
            EP_PLANT, {"showPlantImage": "true", "showParallelGroups": "true"}
        ) or {}
        rows = r.get("rows") or []
        if not rows:
            return {}
        plant = rows[0]
        self.plant_id = _i(plant.get("plantId"), 0) or None
        inv = (plant.get("inverters") or [{}])[0]
        return {
            "plant_id": self.plant_id,
            "plant_name": plant.get("name", ""),
            "status_text": plant.get("statusLocaleText") or plant.get("statusText", ""),
            "today_yielding_text": plant.get("todayYieldingText", ""),
            "total_yielding_text": plant.get("totalYieldingText", ""),
            "standard": inv.get("standard", ""),
            "fw_version": _i(inv.get("fwVersion"), -1),
            "hardware_version": _i(inv.get("hardwareVersion"), -1),
            "power_rating": _i(inv.get("powerRating"), -1),
            "machine_type": _i(inv.get("machineType"), -1),
            "protocol_version": _i(inv.get("protocolVersion"), -1),
            "model": inv.get("model"),
            "battery_type": inv.get("batteryType", ""),
        }

    async def get_dongle(self) -> dict:
        if not self.plant_id:
            return {}
        # ⚠️ response KHÔNG có key `success` → kiểm tra `rows`
        # ⚠️ `lost` là CHUỖI "False"/"True"
        r = await self._post(
            EP_DATALOG, {"plantId": str(self.plant_id), "page": "1", "rows": "10"}
        ) or {}
        rows = r.get("rows") or []
        if not rows:
            return {}
        d = rows[0]
        return {
            "sn": d.get("datalogSn", ""),
            "lost": str(d.get("lost", "")).strip().lower() == "true",
            "last_update": d.get("lastUpdateTime", ""),
            "firmware": d.get("firmwareVersion", ""),
            "type": d.get("datalogType", ""),
            "type_text": d.get("datalogTypeText", ""),
            "server_id": d.get("serverId", ""),
        }

    async def get_events(self, rows: int = 5) -> dict:
        if not self.plant_id:
            return {}
        r = await self._post(
            EP_EVENT,
            {
                "plantId": str(self.plant_id),
                "page": "1",
                "rows": str(rows),
                "language": "vi",  # server trả text tiếng Việt sẵn
            },
        ) or {}
        if not r.get("success"):
            return {}
        items = [
            {
                "record_id": e.get("recordId", ""),
                "code": e.get("event", ""),
                "type_text": e.get("eventTypeText", ""),
                "text": e.get("eventText", ""),
                "status": e.get("status", ""),
                "start": e.get("startTime", ""),
                "renormal": e.get("renormalTime", ""),
            }
            for e in (r.get("rows") or [])[:rows]
        ]
        if not items:
            return {}
        last = items[0]
        return {**last, "count": len(items), "recent": items}

    async def get_battery(self) -> dict:
        """Số chu kỳ + cell max/min. ⚠️ KHÔNG có `soh`; `fullCapacity` = 0."""
        r = await self._post(EP_BATTERY, {"serialNum": self.serial}) or {}
        if not r.get("success"):
            return {}
        mx, mn = _i(r.get("globalMaxCellVoltage")), _i(r.get("globalMinCellVoltage"))
        return {
            "cycles": _i(r.get("bmsCycleCnt")),
            "cell_max_mv": mx,
            "cell_min_mv": mn,
            "cell_delta_mv": (mx - mn) if (mx and mn) else 0,
            "cell_max_temp_c": round(_i(r.get("globalMaxCellTemp")) / 10, 1),
            "cell_min_temp_c": round(_i(r.get("globalMinCellTemp")) / 10, 1),
            "status": r.get("batStatus", ""),
            "power_w": _i(r.get("batPower")),
            "has_cell_extremes": bool(r.get("hasCellExtremes")),
        }

    async def get_quick_status(self) -> dict:
        r = await self._post(EP_QUICK_STATUS, {"inverterSn": self.serial}) or {}
        if not r.get("success"):
            return {}
        charging = bool(r.get("hasUnclosedQuickChargeTask"))
        discharging = bool(r.get("hasUnclosedQuickDischargeTask"))
        return {
            "charging": charging,
            "discharging": discharging,
            "charge_status": r.get("unclosedQuickChargeTaskStatus", "") if charging else "",
            "discharge_status": r.get("unclosedQuickDischargeTaskStatus", "") if discharging else "",
            "remain_charge_s": _i(r.get("remainTimeBeforeQuickChargeStop")) if charging else 0,
            "remain_discharge_s": _i(r.get("remainTimeBeforeQuickDischargeStop")) if discharging else 0,
        }

    async def get_config_bits(self) -> dict:
        """Trạng thái bit cấu hình nhóm HR[179] (remoteRead/read) — CHỈ ĐỌC."""
        r = await self._post(
            EP_REMOTE_READ,
            {
                "inverterSn": self.serial,
                "startRegister": str(CONFIG_BIT_BLOCK),
                "pointNumber": "40",
                "autoRetry": "true",
            },
        ) or {}
        if not r.get("success"):
            return {}
        return {k: bool(r[k]) for k in CONFIG_BIT_KEYS if k in r}

    async def get_day_curve(self, date_text: str) -> dict:
        r = await self._post(
            EP_DAY_CURVE, {"serialNum": self.serial, "dateText": date_text}
        ) or {}
        rows = r.get("data") or []
        if not r.get("success") or not rows:
            return {}
        # Chia LÊN, không chia xuống: với 223 điểm/ngày, `len // 72` = 3 → 75 điểm,
        # vượt giới hạn 16 KB/entity của HA. `-(-a // b)` cho ceil để luôn ≤ cap.
        step = max(1, -(-len(rows) // DAY_CURVE_MAX_POINTS))
        points = []
        for x in rows[::step]:
            points.append(
                {
                    "time": x.get("time", ""),
                    "solarPv": _i(x.get("solarPv")),
                    "gridPower": _i(x.get("gridPower")),
                    "battery": _i(x.get("batteryDischarging")),
                    "consumption": _i(x.get("consumption")),
                    "soc": _i(x.get("soc")),
                }
            )
        return {"date": date_text, "count": len(points), "points": points} if points else {}

    async def get_total_years(self) -> dict:
        r = await self._post(EP_TOTAL_COLUMN, {"serialNum": self.serial}) or {}
        if not r.get("success"):
            return {}
        out: dict[str, dict] = {}
        for x in r.get("data") or []:
            pv = _i(x.get("ePv1Day")) + _i(x.get("ePv2Day")) + _i(x.get("ePv3Day"))
            out[str(x.get("year"))] = {
                "pv": round(pv / 10, 1),
                "import": round(_i(x.get("eToUserDay")) / 10, 1),
                "export": round(_i(x.get("eToGridDay")) / 10, 1),
                "consumption": round(_i(x.get("eConsumptionDay")) / 10, 1),
            }
        return out

    async def get_firmware(self, standard_prefix: str = "") -> dict:
        """Danh mục firmware theo loại thiết bị; chọn loại khớp `standard` của inverter."""
        pref = (standard_prefix or "").strip().lower()
        best: dict | None = None
        for dev in FIRMWARE_TYPES:
            r = await self._post(
                EP_FIRMWARE_BY_TYPE, dict(FIRMWARE_BASE, firmwareDeviceType=dev), base=MAJOR_URL
            ) or {}
            rows = r.get("rows") or []
            if not rows:
                continue

            def _ver(x: dict) -> int:
                return max(_i(x.get("v1"), -1), _i(x.get("v2"), -1), _i(x.get("v3"), -1))

            matched = [
                x for x in rows if pref and str(x.get("standard", "")).lower().startswith(pref)
            ]
            use = matched or rows
            cand = {
                "device_type": dev,
                "count": len(rows),
                "matched": len(matched),
                "latest_version": max([_ver(x) for x in use] or [-1]),
                "items": [
                    {
                        "file": x.get("fileName", ""),
                        "standard": x.get("standard", ""),
                        "v1": x.get("v1"),
                        "v2": x.get("v2"),
                        "v3": x.get("v3"),
                        "record_id": x.get("recordId", ""),
                    }
                    for x in use[:12]
                ],
            }
            if matched:
                return cand
            if best is None or cand["count"] > best["count"]:
                best = cand
        return best or {}

    # ── Tổng hợp 1 lần refresh ─────────────────────────────────
    async def async_fetch_all(self, slow: bool, date_text: str) -> dict:
        """Gọi các endpoint cần thiết. `slow=True` → thêm firmware + chuỗi ngày/năm."""
        plant = await self.get_plant()
        runtime = await self.get_runtime()
        energy = await self.get_energy()
        data = {
            "plant": plant,
            "runtime": runtime,
            "energy": energy,
            "dongle": await self.get_dongle(),
            "event": await self.get_events(),
            "battery": await self.get_battery(),
            "quick": await self.get_quick_status(),
            "bits": await self.get_config_bits(),
            "green": {
                "co2_ton": _num_text(energy.get("totalCo2ReductionText")),
                "coal_kg": _num_text(energy.get("totalCoalReductionText")),
                "trees": _num_text(energy.get("totalTreeEquivalentText")),
            },
            "health": {
                "cloud_ok": bool(runtime or energy),
                "has_runtime": bool(runtime.get("hasRuntimeData")),
                "has_today": bool(energy.get("hasTodayData")),
                "lost": str((runtime or energy).get("lost", "")).strip().lower() == "true",
                "pinv": _i(runtime.get("pinv")),
                "prec": _i(runtime.get("prec")),
                "fw_code": energy.get("fwCode") or runtime.get("fwCode") or "",
                "power_rating": energy.get("powerRatingText", ""),
            },
        }
        if slow:
            data["firmware"] = await self.get_firmware(plant.get("standard", ""))
            data["day_curve"] = await self.get_day_curve(date_text)
            data["total_years"] = await self.get_total_years()
        return data
