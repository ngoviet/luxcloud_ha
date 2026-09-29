"""Kiểm chứng đường GHI trên HA THẬT — chỉ ghi giá trị TRÙNG trạng thái hiện tại.

Mục đích: chứng minh `remoteSet/functionControl` chạy được end-to-end (cloud → dongle →
inverter) mà **không đổi hành vi của inverter**. Vì vậy script CHỈ ghi khi giá trị cần ghi
bằng đúng giá trị đang đọc được; bit nào đang bật thì bỏ qua và báo rõ.

KHÔNG đụng tới quick charge/discharge — bấm start sẽ thật sự nạp/xả pin.
"""
from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")  # console Windows cp1252 — CLAUDE.md §3.9

sys.path.insert(0, "tools")
import hass  # noqa: E402

SENSOR = "sensor.luxcloud_bit_cau_hinh_hr_179_dang_bat"
BITS = (
    "FUNC_GRID_PEAK_SHAVING",
    "FUNC_GEN_PEAK_SHAVING",
    "FUNC_ACTIVE_POWER_LIMIT_MODE",
    "FUNC_RSD_DISABLE",  # bit KHÔNG có switch → chứng minh service dùng được
)


def read_bits() -> dict:
    status, data = hass.api(f"/api/states/{SENSOR}")
    if status != 200:
        raise SystemExit(f"!! không đọc được {SENSOR}: HTTP {status}")
    return data.get("attributes", {}).get("bits") or {}


def set_bit(function: str, enable: bool) -> tuple[int, object]:
    return hass.api(
        "/api/services/luxcloud_ha/set_bit",
        payload={"function": function, "enable": enable},
        method="POST",
    )


def main() -> int:
    before = read_bits()
    print("trạng thái TRƯỚC:", json.dumps(before, ensure_ascii=False))

    results = []
    for bit in BITS:
        current = bool(before.get(bit))
        if current:
            print(f"  BỎ QUA {bit}: đang BẬT — ghi false sẽ đổi hành vi inverter")
            results.append((bit, "skipped", None))
            continue
        status, body = set_bit(bit, False)
        ok = status == 200
        print(f"  ghi {bit}=false -> HTTP {status} {'OK' if ok else body}")
        results.append((bit, "written" if ok else "failed", status))

    after = read_bits()
    print("trạng thái SAU  :", json.dumps(after, ensure_ascii=False))

    # Regression cho bug `vol.Coerce(bool)`: chuỗi "false" là TRUTHY trong Python.
    # Bản cũ vì thế ghi enable=True — tức BẬT bit trong khi người dùng gõ "false".
    # Ở đây gửi đúng chuỗi đó cho một bit đang tắt và khẳng định nó VẪN tắt.
    str_results = []
    for bit in BITS:
        if after.get(bit):
            print(f"  BỎ QUA kiểm chuỗi cho {bit}: đang BẬT")
            continue
        status, _ = hass.api(
            "/api/services/luxcloud_ha/set_bit",
            payload={"function": bit, "enable": "false"},
            method="POST",
        )
        print(f"  ghi {bit} với CHUỖI \"false\" -> HTTP {status}")
        str_results.append((bit, status))

    final = read_bits()
    flipped = {k for k in final if final.get(k) != after.get(k)}

    changed = {k for k in set(before) | set(final) if before.get(k) != final.get(k)}
    failed = [b for b, state, _ in results if state == "failed"]
    written = [b for b, state, _ in results if state == "written"]
    str_failed = [b for b, status in str_results if status != 200]

    print(f"\nđã ghi thật: {written}")
    print(f"đã gửi chuỗi \"false\": {[b for b, _ in str_results]}")
    if flipped:
        print(f"!! CẢNH BÁO: bit bị lật bởi chuỗi \"false\": {flipped}")
    if changed:
        print(f"!! CẢNH BÁO: bit đổi trạng thái: {changed}")
    if failed or str_failed:
        print(f"!! ghi thất bại: {failed + str_failed}")
    ok = bool(written) and not changed and not flipped and not failed and not str_failed
    print(f"KẾT LUẬN: {'ĐẠT' if ok else 'CẦN XEM LẠI'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
