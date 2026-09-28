"""Windows-only stub of the POSIX `fcntl` module, for running the test suite.

`homeassistant.runner` does `import fcntl` at import time and only calls
`fcntl.flock(...)` inside a function the test suite never reaches. Home Assistant's
test harness (pytest-homeassistant-custom-component) imports that module, so on
Windows collection dies with `ModuleNotFoundError: No module named 'fcntl'`.

`tools/setup_tests.py` copies this file into `.venv/Lib/site-packages/`. It is NOT
installed on Linux/macOS, where the real module exists — CI never uses it.
"""
from __future__ import annotations

LOCK_EX = 2
LOCK_NB = 4
LOCK_SH = 1
LOCK_UN = 8


def flock(fd, operation):  # noqa: ANN001, ARG001
    """No-op: file locking is irrelevant to these tests."""
    return None


def lockf(fd, cmd, len=0, start=0, whence=0):  # noqa: ANN001, ARG001, A002
    return None


def fcntl(fd, cmd, arg=0):  # noqa: ANN001, ARG001, A002
    return 0


def ioctl(fd, request, arg=0, mutate_flag=True):  # noqa: ANN001, ARG001, A002
    return 0
