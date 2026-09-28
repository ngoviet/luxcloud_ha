"""Dựng `.venv` để chạy bộ test (`tests/`) — một lệnh, chạy được cả Windows lẫn Linux.

Vì sao cần script này thay vì chỉ `pip install -r requirements_test.txt`?

`pytest-homeassistant-custom-component` (harness chính thức để test custom integration của HA)
chỉ chạy tự nhiên trên Linux/macOS. Trên Windows nó chết vì hai module **chỉ có trên POSIX**:

  * `homeassistant.runner`          → `import fcntl`
  * `homeassistant.util.resource`   → `import resource`

Cả hai chỉ dùng trong hàm mà bộ test không bao giờ gọi tới, nên script này copy stub trong
`tools/win32_stubs/` vào `site-packages` của venv **chỉ trên Windows**. Linux/CI dùng module thật.

Dùng:
    python tools\\setup_tests.py            # dựng/ cập nhật .venv
    python tools\\setup_tests.py --run      # dựng xong chạy pytest luôn
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import venv
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # console Windows là cp1252 — xem CLAUDE.md §3.9

REPO = Path(__file__).resolve().parent.parent
VENV_DIR = REPO / ".venv"
REQUIREMENTS = REPO / "requirements_test.txt"
STUB_DIR = REPO / "tools" / "win32_stubs"


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(cmd: list[str], *, quiet: bool = False) -> int:
    if not quiet:
        print("  $ " + " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=False).returncode


def site_packages(python: Path) -> Path:
    """Thư mục site-packages THẬT của venv.

    Không dùng `site.getsitepackages()[0]`: trong venv nó trả về chính thư mục gốc
    của venv (`.venv`), không phải `.venv/Lib/site-packages`.
    """
    out = subprocess.run(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(out.stdout.strip())


def ensure_venv() -> Path:
    python = venv_python()
    if python.exists():
        print(f"[1/4] venv đã có: {VENV_DIR}")
        return python
    print(f"[1/4] tạo venv: {VENV_DIR}")
    venv.EnvBuilder(with_pip=True, clear=False).create(VENV_DIR)
    if not python.exists():
        raise SystemExit(f"tạo venv xong nhưng không thấy {python}")
    return python


def install_requirements(python: Path) -> None:
    print("[2/4] cài phụ thuộc test (tải Home Assistant ~vài trăm MB ở lần đầu)")
    if run([str(python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"]) != 0:
        raise SystemExit("nâng cấp pip thất bại")
    if run([str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)]) != 0:
        raise SystemExit("cài requirements_test.txt thất bại")


def install_windows_stubs(python: Path) -> int:
    """Copy stub POSIX vào site-packages. Trả về số file đã copy."""
    if sys.platform != "win32":
        print("[3/4] không phải Windows → dùng module POSIX thật, bỏ qua stub")
        return 0
    target = site_packages(python)
    copied = 0
    for stub in sorted(STUB_DIR.glob("*.py")):
        dest = target / stub.name
        dest.write_text(stub.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"      stub: {stub.name} → {dest}")
        copied += 1
    print(f"[3/4] đã đặt {copied} stub POSIX cho Windows")
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="chạy pytest ngay sau khi dựng xong")
    parser.add_argument(
        "--stubs-only",
        action="store_true",
        help="chỉ đặt lại stub POSIX (khi venv đã có sẵn)",
    )
    args = parser.parse_args()

    python = venv_python()
    if args.stubs_only:
        if not python.exists():
            raise SystemExit(f"chưa có venv ở {VENV_DIR} — chạy không kèm --stubs-only trước")
        install_windows_stubs(python)
        return 0

    python = ensure_venv()
    install_requirements(python)
    install_windows_stubs(python)

    print("[4/4] xong")
    print(f"\nChạy test:\n  {python} -m pytest -q")
    print(f"Chỉ module thuần (nhanh):\n  {python} -m pytest tests/test_api_parsing.py -q")

    if args.run:
        print("\n=== pytest ===")
        return run([str(python), "-m", "pytest", "-q"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
