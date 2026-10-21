"""Năng lượng theo kỳ hoá đơn + theo năm, và tiền tiết kiệm (giá điện bậc thang EVN).

Thuần Python, không gọi mạng — `api.get_periods` lấy dữ liệu thô rồi đưa vào đây.

Nguồn số liệu (đo thật 2026-10-21):
  • `api/inverterChart/monthColumn` {serialNum, year, month} → `data` = 1 dòng/ngày
    (đủ 31 dòng, ngày chưa tới = 0), khoá `day`.
  • `api/inverterChart/yearColumn`  {serialNum, year}        → `data` = 1 dòng/tháng, khoá `month`.
  Mọi trường năng lượng là **0,1 kWh** (chia 10).

Cách tính giữ ĐÚNG như `luxpower_cloud_fetcher.py` (HA-Config) mà integration này thay thế:
kỳ hoá đơn bắt đầu ngày `billing_day` tháng trước tới ngày `billing_day - 1` tháng này;
năm là năm dương lịch; tiết kiệm = tiền điện nếu KHÔNG có NLMT (theo tổng tiêu thụ)
− tiền điện thực trả (theo điện mua lưới), cả hai tính bậc thang + VAT.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

# Trường → khoá thô trong response (cộng nếu nhiều khoá).
_FIELDS: dict[str, tuple[str, ...]] = {
    "pv": ("ePv1Day", "ePv2Day", "ePv3Day"),
    "grid_import": ("eToUserDay",),
    "grid_export": ("eToGridDay",),
    "charge": ("eChgDay",),
    "discharge": ("eDisChgDay",),
    "eps": ("eEpsDay",),
    "consumption": ("eConsumptionDay",),
}
METRICS = tuple(_FIELDS)

# Giá bán lẻ điện sinh hoạt — 6 bậc (đồng/kWh, chưa VAT).
# Nguồn: Quyết định 4495/QĐ-BCT ngày 28/12/2024 (áp dụng từ 2025).
TIERS: tuple[tuple[float, int], ...] = (
    (50, 1984),
    (100, 2050),
    (200, 2380),
    (300, 2998),
    (400, 3350),
    (float("inf"), 3460),
)
VAT = 1.08


def _raw(entry: dict, key: str) -> int:
    try:
        return int(float(entry.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def _sum_raw(entries: Iterable[dict]) -> dict[str, float]:
    """Cộng các dòng thô rồi đổi 0,1 kWh → kWh (làm tròn 1 số lẻ như cloud)."""
    total = dict.fromkeys(METRICS, 0)
    for entry in entries:
        for metric, keys in _FIELDS.items():
            total[metric] += sum(_raw(entry, k) for k in keys)
    return {k: round(v / 10, 1) for k, v in total.items()}


def billing_cycle(today: date, billing_day: int) -> tuple[date, date]:
    """(ngày đầu, ngày cuối) của kỳ hoá đơn chứa `today`.

    `billing_day = 27` ⇒ 27/tháng trước → 26/tháng này (hoặc 27/tháng này → 26/tháng sau
    khi đã qua ngày 27). `billing_day = 1` ⇒ đúng tháng dương lịch.
    """
    if today.day >= billing_day:
        start = today.replace(day=billing_day)
    else:
        prev_last = today.replace(day=1) - timedelta(days=1)
        start = prev_last.replace(day=billing_day)
    # ngày đầu kỳ sau = cùng `billing_day` của tháng kế tiếp
    nxt = (start.replace(day=1) + timedelta(days=32)).replace(day=billing_day)
    return start, nxt - timedelta(days=1)


def months_needed(today: date, billing_day: int) -> list[tuple[int, int]]:
    """Các (năm, tháng) cần gọi monthColumn: tháng của kỳ hoá đơn (tới hôm nay) + tháng của hôm qua."""
    start, _ = billing_cycle(today, billing_day)
    wanted = [(start.year, start.month), (today.year, today.month)]
    yesterday = today - timedelta(days=1)
    wanted.append((yesterday.year, yesterday.month))
    return list(dict.fromkeys(wanted))


def tiered_cost(kwh: float) -> int:
    """Tiền điện (VND, đã VAT) cho `kwh` theo bậc thang."""
    total = 0.0
    remaining = kwh
    prev = 0.0
    for limit, price in TIERS:
        step = min(remaining, limit - prev)
        if step <= 0:
            break
        total += step * price
        remaining -= step
        prev = limit
    return round(total * VAT)


def savings(consumption: float, grid_import: float) -> int:
    """Tiền tiết kiệm nhờ NLMT trong một kỳ (VND)."""
    if consumption <= 0 or grid_import < 0:
        return 0
    return tiered_cost(consumption) - tiered_cost(grid_import)


def _days_in(rows: list[dict], first: int, last: int) -> list[dict]:
    return [r for r in rows if first <= _raw(r, "day") <= last]


def build_periods(
    today: date,
    billing_day: int,
    month_rows: dict[tuple[int, int], list[dict] | None],
    year_rows: list[dict] | None,
) -> dict[str, dict[str, Any]]:
    """Ghép kỳ hoá đơn / năm / hôm qua từ dữ liệu thô.

    Thiếu BẤT KỲ tháng nào của một phần ⇒ phần đó rỗng (`{}`), KHÔNG cộng thiếu:
    một tổng thiếu nửa kỳ ghi vào lịch sử trông như sản lượng tụt thật.
    """
    out: dict[str, dict[str, Any]] = {"month": {}, "year": {}, "yesterday": {}}

    start, end = billing_cycle(today, billing_day)
    parts: list[dict] = []
    complete = True
    for year, month in dict.fromkeys([(start.year, start.month), (today.year, today.month)]):
        rows = month_rows.get((year, month))
        if rows is None:
            complete = False
            break
        first = start.day if (year, month) == (start.year, start.month) else 1
        last = today.day if (year, month) == (today.year, today.month) else 31
        parts.extend(_days_in(rows, first, last))
    if complete:
        month = _sum_raw(parts)
        out["month"] = {
            **month,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "savings": savings(month["consumption"], month["grid_import"]),
        }

    if year_rows is not None:
        year = _sum_raw(year_rows)
        out["year"] = {
            **year,
            "year": today.year,
            "savings": savings(year["consumption"], year["grid_import"]),
        }

    yday = today - timedelta(days=1)
    rows = month_rows.get((yday.year, yday.month))
    if rows is not None:
        out["yesterday"] = {**_sum_raw(_days_in(rows, yday.day, yday.day)), "date": yday.isoformat()}
    return out


def merge_periods(
    new: dict[str, dict] | None,
    cached: dict[str, dict] | None,
    today: date,
    billing_day: int,
) -> dict[str, dict]:
    """Phần nào lần này lỗi thì giữ bản cũ — NHƯNG chỉ khi bản cũ vẫn cùng kỳ/năm/ngày.

    Cloud chập chờn 1 lần không nên làm sensor tháng thành `unknown` rồi quay lại;
    còn bản cũ của kỳ TRƯỚC thì không được trình bày như kỳ này.
    """
    new = dict(new or {})
    cached = cached or {}
    expect = {
        "month": ("start", billing_cycle(today, billing_day)[0].isoformat()),
        "year": ("year", today.year),
        "yesterday": ("date", (today - timedelta(days=1)).isoformat()),
    }
    for part, (marker, value) in expect.items():
        if new.get(part):
            continue
        old = cached.get(part) or {}
        new[part] = old if old.get(marker) == value else {}
    return new
