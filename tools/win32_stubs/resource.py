"""Windows-only stub of the POSIX `resource` module, for running the test suite.

`homeassistant.util.resource` imports `resource` at import time and uses
`getrlimit`/`setrlimit` only inside `set_open_file_descriptor_limit()`, which the
test suite never calls. Same rationale as the sibling `fcntl.py` stub.

`tools/setup_tests.py` copies this file into `.venv/Lib/site-packages/`. It is NOT
installed on Linux/macOS, where the real module exists — CI never uses it.
"""
from __future__ import annotations

RLIMIT_NOFILE = 7
RLIMIT_CPU = 0
RLIM_INFINITY = -1


def getrlimit(resource_id):  # noqa: ANN001, ARG001
    return (RLIM_INFINITY, RLIM_INFINITY)


def setrlimit(resource_id, limits):  # noqa: ANN001, ARG001
    return None
