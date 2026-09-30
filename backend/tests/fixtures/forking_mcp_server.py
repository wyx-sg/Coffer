"""A stand-in stdio MCP server that forks a grandchild before it serves.

Run as ``python forking_mcp_server.py <pidfile> <mode> [fake-server args...]``:
it starts a long-sleeping child (which stays in this process's group), writes
that child's pid to ``<pidfile>``, and then either serves MCP through
``fake_mcp_server.py`` (``mode=serve``) or exits with status 1 after printing a
line on stderr (``mode=exit``). A test asserts the grandchild is gone once the
probe that started this process has finished.
"""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

_FAKE = Path(__file__).with_name("fake_mcp_server.py")


def main() -> None:
    pidfile, mode, *rest = sys.argv[1:]
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    Path(pidfile).write_text(str(child.pid))
    if mode == "exit":
        sys.stderr.write("fatal: cannot start\n")
        sys.stderr.flush()
        sys.exit(1)
    sys.argv = [str(_FAKE), *rest]
    runpy.run_path(str(_FAKE), run_name="__main__")


if __name__ == "__main__":
    main()
