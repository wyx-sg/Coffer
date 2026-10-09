"""From the repo root: ``python -m e2e.installed.mcp --out DIR [--daemon-json P] [--shim P]``."""

import sys

from e2e.installed.mcp.runner import entry

sys.exit(entry())
