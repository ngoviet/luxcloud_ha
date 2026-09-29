"""Nghiệm thu LIVE: file diagnostics thật của HA có lọt dữ liệu nhạy cảm không.

Vì sao cần script này chứ không chỉ unit test: fixture trong `tests/` chỉ chứa những
field mình BIẾT. Cloud trả thêm field mới (vd `serialNum` trong `runtime`/`energy`)
thì unit test vẫn xanh trong khi file user tải lên issue vẫn lộ serial inverter —
đúng cái đã xảy ra một lần. Chỉ kéo file THẬT từ HA mới bắt được.

Chạy: python tools/probe_diagnostics_live.py
Exit 0 = ĐẠT, 1 = có rò rỉ, 2 = không gọi được HA.
"""
from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")  # console Windows cp1252 — CLAUDE.md §3.9

sys.path.insert(0, "tools")
import hass  # noqa: E402

DOMAIN = "luxcloud_ha"


def main() -> int:
    status, entries = hass.api("/api/config/config_entries/entry")
    if status != 200:
        print(f"!! không đọc được config entry: HTTP {status}")
        return 2
    mine = [e for e in entries if e.get("domain") == DOMAIN]
    if not mine:
        print(f"!! không có config entry nào cho domain {DOMAIN}")
        return 2

    exit_code = 0
    for entry in mine:
        entry_id = entry["entry_id"]
        status, payload = hass.api(f"/api/diagnostics/config_entry/{entry_id}")
        print(f"\n=== {entry.get('title')} ({entry_id}) ===")
        if status != 200:
            print(f"!! HTTP {status}: {payload}")
            return 2

        blob = json.dumps(payload, ensure_ascii=False)
        our = payload.get("data") or {}
        cloud = our.get("data") or {}
        our_blob = json.dumps(our, ensure_ascii=False)

        # Giá trị nhận dạng lấy từ chính dữ liệu, không hardcode.
        serials = {
            str(entry.get("title", "")).split()[-1],
            (cloud.get("dongle") or {}).get("sn") or "",
        }
        serials = {s for s in serials if s and s != "**REDACTED**"}

        print(f"  kích thước file      : {len(blob)} ký tự")
        print(f"  giá trị đã che       : {our_blob.count('**REDACTED**')}")

        leaks = []
        for needle in sorted(serials):
            if needle in our_blob:
                leaks.append(f"serial {needle!r}")
        if "@" in our_blob:
            leaks.append("ký tự '@' (email tài khoản)")

        for label in leaks:
            print(f"  !! RÒ RỈ: {label}")

        # Che quá tay cũng là lỗi: file phải còn dùng được để chẩn đoán.
        useful = (cloud.get("battery") or {}).get("cycles") is not None
        print(f"  battery.cycles       : {(cloud.get('battery') or {}).get('cycles')}")
        print(f"  health.fw_code       : {(cloud.get('health') or {}).get('fw_code')}")
        print(f"  day_curve đã cắt     : {(cloud.get('day_curve') or {}).get('_trimmed')}")
        if not useful:
            print("  !! mất dữ liệu chẩn đoán — che quá tay?")

        redacted = our_blob.count("**REDACTED**")
        if leaks or not useful or redacted < 3:
            exit_code = 1

    print(f"\nKẾT LUẬN: {'ĐẠT' if exit_code == 0 else 'CẦN XEM LẠI'}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
