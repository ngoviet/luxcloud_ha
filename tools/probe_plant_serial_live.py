"""Kiểm chứng trên cloud THẬT: `getPlantList` có trả serial inverter không.

Config flow (v1.2.4) chỉ chặn serial gõ sai khi cloud CÓ liệt kê serial trong
`rows[].inverters[]` (`api.serial_in_account` = True/False); không có field nào
thì là `None` và kiểm tra không có tác dụng. Script này đo điều đó.

Chạy BÊN TRONG container HA: tài khoản lấy từ config entry đang chạy, gọi qua
chính `LuxCloudApi` đã deploy. CHỈ in tên field + kết quả khớp — KHÔNG in
serial, email, mật khẩu hay tên plant.
"""
from __future__ import annotations

import base64
import sys

sys.stdout.reconfigure(encoding="utf-8")  # console Windows cp1252 — CLAUDE.md §3.9

sys.path.insert(0, "tools")
import hass  # noqa: E402

IN_CONTAINER = r'''
import asyncio, json, sys
sys.path.insert(0, "/config")
import aiohttp
from custom_components.luxcloud_ha.api import LuxCloudApi
from custom_components.luxcloud_ha.const import EP_PLANT, REGIONS, DEFAULT_REGION

SERIAL_HINTS = ("sn", "serial")

async def main():
    entries = json.load(open("/config/.storage/core.config_entries"))["data"]["entries"]
    entries = [e for e in entries if e["domain"] == "luxcloud_ha"]
    print("entry luxcloud_ha:", len(entries))
    for e in entries:
        d = e["data"]
        base = REGIONS.get(str(d.get("region", DEFAULT_REGION)).lower(), REGIONS[DEFAULT_REGION])
        async with aiohttp.ClientSession() as session:
            api = LuxCloudApi(session, base, d["account"], d["password"], d["serial"])
            await api.login()
            raw = await api._post(EP_PLANT, {"showPlantImage": "true", "showParallelGroups": "true"}) or {}
            rows = raw.get("rows") or []
            print("plants:", len(rows))
            for i, plant in enumerate(rows):
                invs = plant.get("inverters") or []
                print(f"  plant[{i}] inverters: {len(invs)}")
                for j, inv in enumerate(invs):
                    keys = sorted(inv)
                    hints = [k for k in keys if any(h in k.lower() for h in SERIAL_HINTS)]
                    print(f"    inverter[{j}] {len(keys)} field; field nghi là serial: {hints}")
                    for k in ("serialNum", "sn"):
                        if k in inv:
                            v = str(inv[k] or "").strip().upper()
                            print(f"      {k}: có, rỗng={not v}, khớp serial entry={v == api.serial}")
                    print(f"      tất cả field: {keys}")
            await api.get_plant()
            print("api.serial_in_account =", api.serial_in_account)
            print("api.plant_id khớp với plant chứa serial:", api.plant_id is not None)

asyncio.run(main())
'''


def main() -> int:
    code = base64.b64encode(IN_CONTAINER.encode()).decode()
    out, err = hass.docker(f"echo {code} | base64 -d | python3 -")
    print(out)
    if err.strip():
        # sudo in prompt mật khẩu ra stderr — chỉ hiện dòng khác
        rest = [ln for ln in err.splitlines() if "password for" not in ln.lower()]
        if rest:
            print("stderr:", "\n".join(rest))
    return 0 if "serial_in_account" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
