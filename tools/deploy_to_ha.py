"""Deploy custom_components/luxcloud_ha/ lên Home Assistant qua SSH (base64).

Dùng (từ thư mục gốc repo):
    python tools/deploy_to_ha.py            # deploy toàn bộ integration
    python tools/deploy_to_ha.py --restart  # deploy rồi restart HA

Credential đọc theo thứ tự: biến môi trường HA_HOST/HA_USER/HA_PASS/HA_TOKEN,
rồi tới file `.env` cùng thư mục, rồi tới `../HA-Config/.env` (nơi đang giữ sẵn).

Hai điều đã học được khi làm việc với setup này:
  * Host KHÔNG có `sftp-server` → phải shell + base64, không dùng SFTP.
  * `base64 -d > file` KHÔNG tự tạo thư mục cha → phải `mkdir -p` trước, nếu không
    md5 sẽ lệch mà không có thông báo lỗi rõ ràng.
"""
from __future__ import annotations

import base64
import hashlib
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

import paramiko

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "custom_components" / "luxcloud_ha"
REMOTE = "/config/custom_components/luxcloud_ha"
DOMAIN = "luxcloud_ha"


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
HOST, USER, PASSWORD = ENV.get("HA_HOST", "192.168.10.15"), ENV.get("HA_USER", "vokupt"), ENV.get("HA_PASS", "")
TOKEN, BASE = ENV.get("HA_TOKEN", ""), f"http://{ENV.get('HA_HOST', '192.168.10.15')}:8123"


def connect() -> paramiko.SSHClient:
    if not PASSWORD:
        sys.exit("Thiếu HA_PASS (đặt trong .env hoặc biến môi trường)")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    return client


def run(client: paramiko.SSHClient, cmd: str) -> tuple[str, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=300)
    return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")


def sudo(client: paramiko.SSHClient, cmd: str) -> str:
    out, err = run(client, f"echo '{PASSWORD}' | sudo -S sh -c \"{cmd}\"")
    return out + err


def deploy() -> bool:
    client = connect()
    try:
        files = sorted(p for p in SRC.rglob("*")
                       if p.is_file() and "__pycache__" not in p.parts)
        sudo(client, f"mkdir -p {REMOTE}")
        for d in sorted({p.parent for p in files}):
            if d != SRC:
                sudo(client, f"mkdir -p {REMOTE}/{d.relative_to(SRC).as_posix()}")
        ok = True
        for f in files:
            rel = f.relative_to(SRC).as_posix()
            b64 = base64.b64encode(f.read_bytes()).decode()
            run(client, f"echo {b64} | sudo sh -c 'base64 -d > {REMOTE}/{rel}'")
            out, _ = run(client, f"md5sum {REMOTE}/{rel}")
            local, remote = hashlib.md5(f.read_bytes()).hexdigest(), (out.split() or ["?"])[0]
            good = local == remote
            ok &= good
            print(f"{'OK      ' if good else 'MISMATCH'} {rel}")
        sudo(client, f"rm -rf {REMOTE}/__pycache__")
        return ok
    finally:
        client.close()


def restart() -> None:
    req = urllib.request.Request(
        f"{BASE}/api/services/homeassistant/restart", data=b"{}",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30)
        print("restart: HTTP 200")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        # Mất kết nối / 503 / 504 khi restart là BÌNH THƯỜNG — HA vẫn khởi động lại.
        print(f"restart: {exc} (lỗi kết nối = đang restart, vẫn đúng)")
    for _ in range(24):
        time.sleep(5)
        try:
            urllib.request.urlopen(
                urllib.request.Request(f"{BASE}/api/config",
                                       headers={"Authorization": f"Bearer {TOKEN}"}), timeout=10)
            print("HA đã trở lại")
            return
        except Exception:  # noqa: BLE001
            continue
    print("!! HA chưa trở lại sau 120 s")


if __name__ == "__main__":
    done = deploy()
    print("deploy:", "OK" if done else "CÓ LỖI")
    if "--restart" in sys.argv and done:
        restart()
    sys.exit(0 if done else 1)
