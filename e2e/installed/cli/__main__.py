"""From the repo root: ``python -m e2e.installed.cli --out DIR [--coffer PATH]``."""

import sys

from e2e.installed.cli.runner import entry

sys.exit(entry())
