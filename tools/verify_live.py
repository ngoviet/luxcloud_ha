"""Nghiệm thu integration luxcloud_ha đang chạy trên HA — tự chứa.

Kiểm tra: config entry, danh sách entity, quan hệ device (inverter ↔ dongle), và
đếm cảnh báo HA deprecate/hỏng CHỈ sau lần boot gần nhất (tránh lẫn log cũ).

Dùng: python tools/verify_live.py
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hass  # noqa: E402

DOMAIN = "luxcloud_ha"
TOOLS = pathlib.Path(__file__).parent


def main() -> int:
    for _ in range(30):
        status, cfg = hass.api("/api/config", timeout=10)
        if status == 200:
            print(f"HA {cfg.get('version')} @ {hass.BASE}")
            break
        time.sleep(5)
    else:
        print("!! HA không trả lời /api/config")
        return 2

    print("\n=== config entry ===")
    _, entries = hass.api("/api/config/config_entries/entry")
    mine = [e for e in entries if e.get("domain") == DOMAIN]
    for e in mine:
        print(f"  {e['entry_id']}  state={e['state']}  title={e.get('title')}")
    if not mine:
        print(f"  !! KHÔNG có entry domain {DOMAIN}")
        return 3

    print("\n=== entity ===")
    _, states = hass.api("/api/states")
    ents = sorted(s for s in states if s["entity_id"].split(".")[1].startswith("luxcloud"))
    print(f"  tổng: {len(ents)}")
    cut = time.strftime("%Y-%m-%dT%H:%M", time.gmtime(time.time() - 900))
    fresh = [s for s in ents if s["last_updated"] > cut]
    print(f"  cập nhật trong 15 phút: {len(fresh)}/{len(ents)}")
    for s in ents:
        attrs = s["attributes"]
        unit = attrs.get("unit_of_measurement", "")
        print(f"    {s['entity_id']:54} = {str(s['state'])[:26]:28} {unit}")

    print("\n=== device registry ===")
    cmds = TOOLS / "ws_cmds_dev.json"
    cmds.write_text(json.dumps([{"type": "config/device_registry/list"}]), encoding="utf-8")
    proc = subprocess.run(
        ["node", str(TOOLS / "ws.js"), str(cmds), "luxcloud"],
        capture_output=True, text=True, encoding="utf-8", cwd=str(TOOLS.parent),
        env=dict(os.environ, HA_TOKEN=hass.HA_TOKEN),
    )
    devices = []
    for line in (proc.stdout or "").splitlines():
        if line.strip().startswith("{"):
            devices.append(json.loads(line))
    for dev in devices:
        print(f"  {dev['name']:18} id={dev['id'][:12]}... via_device_id={str(dev.get('via_device_id'))[:12]}... "
              f"model={dev.get('model')} sw={dev.get('sw_version')}")
    dongle = next((d for d in devices if "Dongle" in d["name"]), None)
    inverter = next((d for d in devices if d["name"] == "LuxCloud"), None)
    if dongle and inverter:
        linked = dongle.get("via_device_id") == inverter.get("id")
        print(f"  → dongle nối đúng inverter: {'OK' if linked else '** SAI **'}")

    print("\n=== log sau lần boot cuối ===")
    out, _ = hass.run(f"echo {hass.shquote(hass.HA_PASS)} | sudo -S docker logs homeassistant 2>&1 | tail -500")
    lines = out.splitlines()
    boots = [i for i, l in enumerate(lines) if "Starting Home Assistant" in l]
    after = lines[boots[-1]:] if boots else lines
    for pattern, label in (
        ("deprecated `via_device` parameter", "via_device (API cũ)"),
        ("calls `device_registry.async_get_device`", "async_get_device (API cũ)"),
        ("luxcloud_ha", "nhắc tới luxcloud_ha"),
    ):
        print(f"  {label:28}: {len([l for l in after if pattern in l])} dòng")
    errors = [l for l in after if "luxcloud" in l.lower() and ("ERROR" in l or "CRITICAL" in l)]
    print(f"  ERROR/CRITICAL của luxcloud_ha : {len(errors)}")
    for line in errors[:5]:
        print("   ", line.strip()[:190])

    ok = bool(mine) and len(ents) == 29 and not errors
    print(f"\nKẾT LUẬN: {'ĐẠT' if ok else 'CẦN XEM LẠI'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
