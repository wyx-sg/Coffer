"""Root test configuration.

Redirect every coffer log file away from the developer's real ``~/.coffer``
before any test imports a module that calls ``configure_logging()`` (e.g.
importing the HTTP app). ``configure_logging`` honours ``COFFER_LOG_DIR``
(see ``coffer.infrastructure.logging.setup._log_dir``); without this, a test
run pollutes the live ``~/.coffer/logs/daemon.log`` and makes it useless for
debugging the real daemon.

This is set at import time — not in a fixture — because conftest.py is imported
before any test module, and some modules call ``configure_logging()`` at import
or app-construction time. ``setdefault`` lets CI override the location.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_LOG_DIR = Path(tempfile.gettempdir()) / "coffer-test-logs"
os.environ.setdefault("COFFER_LOG_DIR", str(_TEST_LOG_DIR))

# Accept any Host header across the suite. The loopback-Host guard
# (``coffer.surfaces.http.host_guard``) exists to stop a DNS-rebound *browser*
# page from reading the daemon's responses; these tests drive the ASGI app
# in-process over httpx/TestClient, where there is no network, no browser and
# therefore no rebinding — but where the transports do send made-up
# authorities like ``testserver``. The guard's own tests clear this variable
# and assert both directions for real.
os.environ.setdefault("COFFER_ALLOWED_HOSTS", "*")
