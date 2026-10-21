"""Test `energy.py`: kỳ hoá đơn, tổng năm, hôm qua, tiền tiết kiệm.

Số kỳ vọng của tiết kiệm lấy từ fetcher cũ (`luxpower_cloud_fetcher.py`) chạy thật
2026-10-21 — integration thay nó nên phải ra ĐÚNG từng đồng.
"""
from __future__ import annotations

from datetime import date

import pytest

from custom_components.luxcloud_ha import energy
from tests import conftest as fx

# ── Kỳ hoá đơn ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("today", "billing_day", "start", "end"),
    [
        (date(2026, 10, 21), 27, date(2026, 9, 27), date(2026, 10, 26)),
        (date(2026, 10, 26), 27, date(2026, 9, 27), date(2026, 10, 26)),
        (date(2026, 10, 27), 27, date(2026, 10, 27), date(2026, 11, 26)),
        (date(2026, 1, 5), 27, date(2025, 12, 27), date(2026, 1, 26)),
        (date(2026, 12, 30), 27, date(2026, 12, 27), date(2027, 1, 26)),
        (date(2026, 3, 1), 27, date(2026, 2, 27), date(2026, 3, 26)),
        (date(2026, 2, 14), 1, date(2026, 2, 1), date(2026, 2, 28)),
        (date(2024, 2, 29), 1, date(2024, 2, 1), date(2024, 2, 29)),
        (date(2026, 12, 31), 1, date(2026, 12, 1), date(2026, 12, 31)),
        (date(2026, 3, 15), 28, date(2026, 2, 28), date(2026, 3, 27)),
    ],
)
def test_billing_cycle(today, billing_day, start, end) -> None:
    assert energy.billing_cycle(today, billing_day) == (start, end)


def test_months_needed_spans_cycle_and_yesterday() -> None:
    assert energy.months_needed(date(2026, 10, 21), 27) == [(2026, 9), (2026, 10)]
    assert energy.months_needed(date(2026, 10, 28), 27) == [(2026, 10)]
    # ngày 1 dương lịch: hôm qua thuộc tháng trước dù kỳ chỉ có tháng này
    assert energy.months_needed(date(2026, 11, 1), 1) == [(2026, 11), (2026, 10)]
    assert energy.months_needed(date(2027, 1, 1), 27) == [(2026, 12), (2027, 1)]


# ── Tiền điện ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("kwh", "expected"),
    [
        (0, 0),
        (50, round(50 * 1984 * 1.08)),
        (100, round((50 * 1984 + 50 * 2050) * 1.08)),
        (450, round((50 * 1984 + 50 * 2050 + 100 * 2380 + 100 * 2998 + 100 * 3350 + 50 * 3460) * 1.08)),
    ],
)
def test_tiered_cost(kwh, expected) -> None:
    assert energy.tiered_cost(kwh) == expected


def test_savings_match_the_legacy_fetcher_to_the_dong() -> None:
    """Đo 2026-10-21: fetcher ra 2 295 653 đ (kỳ) và 8 816 232 đ (năm)."""
    assert energy.savings(746.5, 73.7) == 2295653
    assert energy.savings(3254.7, 895.4) == 8816232


def test_savings_zero_without_consumption() -> None:
    assert energy.savings(0, 0) == 0
    assert energy.savings(10, -1) == 0


# ── Ghép kỳ / năm / hôm qua ────────────────────────────────────


def _rows(days: int = 31, **kw) -> list[dict]:
    return fx.month_column_payload(days, **kw)["data"]


def test_build_periods_sums_the_two_halves_of_a_cycle() -> None:
    today = date(2026, 10, 21)
    out = energy.build_periods(
        today, 27,
        {(2026, 9): _rows(30), (2026, 10): _rows(21)},
        fx.year_column_payload()["data"],
    )
    month = out["month"]
    # 27–30/9 (4 ngày) + 1–21/10 (21 ngày) = 25 ngày × 30,0 kWh PV
    assert month["pv"] == 750.0
    assert month["consumption"] == 750.0
    # mua lưới = 0,d kWh mỗi ngày: (27+28+29+30) + (1+…+21) = 114 + 231 → 34,5 kWh
    assert month["grid_import"] == 34.5
    assert month["eps"] == 1.0  # chỉ ngày 11/10
    assert (month["start"], month["end"]) == ("2026-09-27", "2026-10-26")
    assert month["savings"] == energy.savings(750.0, 34.5)


def test_build_periods_ignores_days_after_today() -> None:
    """Cloud trả đủ 31 dòng; dòng tương lai lỡ có số (sai giờ) cũng không được cộng."""
    out = energy.build_periods(date(2026, 10, 2), 1, {(2026, 10): _rows(31), (2026, 9): _rows(30)}, [])
    assert out["month"]["pv"] == 60.0


def test_build_periods_year_and_yesterday() -> None:
    out = energy.build_periods(
        date(2026, 10, 21), 27,
        {(2026, 9): _rows(30), (2026, 10): _rows(21)},
        fx.year_column_payload()["data"],
    )
    assert out["year"]["pv"] == 2700.0
    assert out["year"]["grid_import"] == 900.0
    assert out["year"]["consumption"] == 3000.0
    assert out["year"]["eps"] == 6.0
    assert out["year"]["year"] == 2026
    assert out["year"]["savings"] == energy.savings(3000.0, 900.0)
    assert out["yesterday"]["date"] == "2026-10-20"
    assert out["yesterday"]["consumption"] == 30.0
    assert out["yesterday"]["grid_import"] == 2.0


def test_yesterday_on_the_first_reads_the_previous_month() -> None:
    """Fetcher cũ trả 0 cho 'hôm qua' vào ngày 1 — bản này đọc tháng trước."""
    out = energy.build_periods(
        date(2026, 11, 1), 27, {(2026, 10): _rows(31), (2026, 11): _rows(1)}, []
    )
    assert out["yesterday"] == {**out["yesterday"], "date": "2026-10-31", "grid_import": 3.1}


def test_missing_month_blanks_the_cycle_instead_of_half_summing() -> None:
    out = energy.build_periods(
        date(2026, 10, 21), 27, {(2026, 9): None, (2026, 10): _rows(21)}, None
    )
    assert out["month"] == {}
    assert out["year"] == {}
    assert out["yesterday"]["consumption"] == 30.0


def test_empty_year_list_is_zero_not_unknown() -> None:
    """Cloud trả `data: []` (đầu năm chưa có số) khác với lỗi: tổng 0 là đúng."""
    out = energy.build_periods(date(2026, 1, 1), 1, {(2026, 1): _rows(0), (2025, 12): _rows(31)}, [])
    assert out["year"]["pv"] == 0.0


# ── Giữ bản cũ khi lỗi ─────────────────────────────────────────


def test_merge_keeps_cached_parts_of_the_same_period() -> None:
    today = date(2026, 10, 21)
    cached = energy.build_periods(
        today, 27, {(2026, 9): _rows(30), (2026, 10): _rows(21)}, fx.year_column_payload()["data"]
    )
    merged = energy.merge_periods({"month": {}, "year": {}, "yesterday": {}}, cached, today, 27)
    assert merged == cached


def test_merge_drops_cached_parts_of_a_previous_period() -> None:
    old_day = date(2026, 10, 26)
    cached = energy.build_periods(
        old_day, 27, {(2026, 9): _rows(30), (2026, 10): _rows(26)}, fx.year_column_payload()["data"]
    )
    merged = energy.merge_periods({}, cached, date(2026, 10, 27), 27)
    assert merged["month"] == {}  # kỳ mới bắt đầu 27/10
    assert merged["yesterday"] == {}  # 'hôm qua' của bản cũ là 25/10
    assert merged["year"] == cached["year"]  # vẫn năm 2026


def test_merge_prefers_fresh_data() -> None:
    today = date(2026, 10, 21)
    fresh = {"month": {"pv": 1.0, "start": "2026-09-27"}, "year": {}, "yesterday": {}}
    cached = {"month": {"pv": 9.0, "start": "2026-09-27"}}
    assert energy.merge_periods(fresh, cached, today, 27)["month"]["pv"] == 1.0
