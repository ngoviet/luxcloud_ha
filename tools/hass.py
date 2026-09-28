"""Helper HA cho repo luxcloud_ha — TỰ CHỨA (không phụ thuộc HA-Config).

Credential đọc theo thứ tự: biến môi trường → `.env` trong repo này → `../HA-Config/.env`.

Dùng:
    python tools/hass.py run "<shell cmd>"
    python tools/hass.py cfgcheck                 # check_config trong container HA
    python tools/hass.py restart                  # restart HA rồi chờ nó trở lại
    python tools/hass.py deploy <local> <remote>
    python tools/hass.py deploydir <local_dir> <remote_dir>
    python tools/hass.py state <entity_id> [...]
    python tools/hass.py states <substring> [...]

Vì sao có file này (bài học đã trả giá, xem CLAUDE.md):
  * host KHÔNG có sftp-server → phải shell + base64
  * `base64 -d > file` KHÔNG tạo thư mục cha → deploy_dir tự `mkdir -p` trước
  * console Windows cp1252 → phải reconfigure stdout sang UTF-8, nếu không script
    chết ngay sau khi deploy xong (đã gặp thật)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent


def load_env() -> dict[str, str]:
    env = dict(os.environ)
    for candidate in (REPO / ".env", REPO.parent / "HA-Config" / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


ENV = load_env()
HOST = ENV.get("HA_HOST", "192.168.10.15")
USER = ENV.get("HA_USER", "vokupt")
HA_PASS = ENV.get("HA_PASS", "")
HA_TOKEN = ENV.get("HA_TOKEN", "")
BASE = ENV.get("HA_URL", f"http://{HOST}:8123").rstrip("/")
HDRS = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}


def shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def ssh() -> paramiko.SSHClient:
    if not HA_PASS:
        raise SystemExit("Thiếu HA_PASS: đặt trong .env của repo này (xem .env.example)")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=HA_PASS, timeout=20)
    return client


def run(cmd: str, timeout: int = 300) -> tuple[str, str]:
    client = ssh()
    try:
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")
    finally:
        client.close()


def docker(cmd: str) -> tuple[str, str]:
    """Chạy trong container HA (KHÔNG phải /tmp của host — hai /tmp khác nhau)."""
    return run(f"echo {shquote(HA_PASS)} | sudo -S docker exec homeassistant sh -c {shquote(cmd)}")


def deploy(local: str | pathlib.Path, remote: str) -> bool:
    p = pathlib.Path(local)
    data = p.read_bytes()
    run(f"echo {base64.b64encode(data).decode()} | sudo sh -c {shquote('base64 -d > ' + remote)}")
    out, _ = run(f"md5sum {remote}")
    local_md5, remote_md5 = hashlib.md5(data).hexdigest(), (out.split() or ["?"])[0]
    ok = local_md5 == remote_md5
    print(f"{'OK      ' if ok else 'MISMATCH'} {remote}\n         local ={local_md5}\n         remote={remote_md5}")
    return ok


def deploy_dir(local: str | pathlib.Path, remote: str) -> bool:
    src = pathlib.Path(local)
    files = sorted(p for p in src.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    run(f"echo {shquote(HA_PASS)} | sudo -S mkdir -p {remote}")
    for d in sorted({p.parent for p in files}):
        if d != src:
            run(f"echo {shquote(HA_PASS)} | sudo -S mkdir -p {remote}/{d.relative_to(src).as_posix()}")
    ok = all(deploy(f, f"{remote}/{f.relative_to(src).as_posix()}") for f in files)
    run(f"echo {shquote(HA_PASS)} | sudo -S rm -rf {remote}/__pycache__")
    return ok


def api(path: str, payload=None, method: str | None = None, timeout: int = 180):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=HDRS,
                                 method=method or ("POST" if data is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except Exception:  # noqa: BLE001
            return exc.code, {"raw": raw[:300]}
    except Exception as exc:  # noqa: BLE001
        return -1, {"err": str(exc)}


def state(entity_id: str) -> dict:
    st, data = api(f"/api/states/{entity_id}")
    return data if st == 200 else {"state": f"HTTP {st}", "attributes": {}}


def cfgcheck() -> int:
    out, err = docker("python -m homeassistant --script check_config -c /config 2>&1 | tail -40")
    txt = out + err
    bad = [l for l in txt.splitlines() if any(k in l.lower() for k in ("error", "invalid", "fail", "warn"))]
    print(txt.strip()[-2500:])
    print(f"\n>>> dòng nghi vấn: {len(bad)}")
    return 1 if bad else 0


def restart(wait: int = 150) -> None:
    started = time.time()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{BASE}/api/services/homeassistant/restart", data=b"{}", headers=HDRS), timeout=30)
        print("restart: HTTP 200")
    except Exception as exc:  # noqa: BLE001
        # MỌI lỗi ở bước này đều bình thường. `RemoteDisconnected` KHÔNG phải URLError
        # nên except hẹp sẽ làm script chết dù HA restart đúng.
        print(f"restart: {type(exc).__name__} (lỗi kết nối = đang restart, vẫn đúng)")
    while time.time() - started < wait:
        time.sleep(5)
        st, data = api("/api/config", timeout=10)
        if st == 200:
            print(f"HA trở lại sau {time.time() - started:.0f}s | {data.get('version')}")
            return
    print(f"!! HA chưa trở lại sau {wait}s")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == "run":
        out, err = run(" ".join(args[1:]))
        print(out.strip()[:6000])
        if err.strip():
            print("[stderr]", err.strip()[:1500])
    elif args[0] == "cfgcheck":
        sys.exit(cfgcheck())
    elif args[0] == "restart":
        restart()
    elif args[0] == "deploy":
        for i in range(1, len(args), 2):
            deploy(args[i], args[i + 1])
    elif args[0] == "deploydir":
        sys.exit(0 if deploy_dir(args[1], args[2]) else 1)
    elif args[0] == "state":
        for entity_id in args[1:]:
            s = state(entity_id)
            print(f"\n### {entity_id} = {s.get('state')}")
            for k, v in (s.get("attributes") or {}).items():
                print(f"    {k}: {json.dumps(v, ensure_ascii=False)[:300]}")
    elif args[0] == "states":
        _, live = api("/api/states")
        for s in sorted(live, key=lambda x: x["entity_id"]):
            if any(x in s["entity_id"] for x in args[1:]):
                print(f"{s['entity_id']:58} = {str(s['state'])[:50]}")
