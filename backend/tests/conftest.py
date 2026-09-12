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

import pytest

_TEST_LOG_DIR = Path(tempfile.gettempdir()) / "coffer-test-logs"
os.environ.setdefault("COFFER_LOG_DIR", str(_TEST_LOG_DIR))

# Same reason, and a far worse failure mode: ``paths.knowledge_root()`` falls
# back to ``$HOME/.coffer/knowledge`` when ``COFFER_KNOWLEDGE_ROOT`` is unset,
# so any test that boots the app without pinning it runs the knowledge
# migration over the developer's REAL vault — moving their files, not just
# writing a log line. Pinned at import time so no test can reach the live tree
# by forgetting a fixture; a test that wants its own tree overrides it per-test
# with monkeypatch, which takes precedence over this default.
_TEST_KNOWLEDGE_ROOT = Path(tempfile.gettempdir()) / "coffer-test-knowledge"
os.environ.setdefault("COFFER_KNOWLEDGE_ROOT", str(_TEST_KNOWLEDGE_ROOT))


@pytest.fixture(autouse=True)
def _isolated_knowledge_root(tmp_path, monkeypatch):
    """Give every test its own knowledge tree.

    The import-time default above is the safety net — it keeps a forgotten
    fixture off the developer's real vault. This is the isolation: the tree is
    shared state on disk, and the migration registers a Resource for every
    collection directory it finds, so one test's leftover folder would show up
    in another test's resource list. A test that wants a specific path (a
    migration walk, say) overrides it with its own monkeypatch, which wins.
    """
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge-root"))


# Accept any Host header across the suite. The loopback-Host guard
# (``coffer.surfaces.http.host_guard``) exists to stop a DNS-rebound *browser*
# page from reading the daemon's responses; these tests drive the ASGI app
# in-process over httpx/TestClient, where there is no network, no browser and
# therefore no rebinding — but where the transports do send made-up
# authorities like ``testserver``. The guard's own tests clear this variable
# and assert both directions for real.
os.environ.setdefault("COFFER_ALLOWED_HOSTS", "*")
