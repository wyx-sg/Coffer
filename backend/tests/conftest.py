"""Root test configuration.

First, before anything imports ``coffer``: the real-home guard
(``tests/support/real_home_guard.py``). ``HOME`` is pointed at a throwaway
directory, every ``COFFER_*`` variable inherited from the developer's shell is
stripped, and an audit hook refuses — and records — any filesystem, SQLite or
spawn event under the real home's ``.coffer`` / agent config trees. A test that
trips it fails in teardown even when the code under test swallowed the
``PermissionError``. See ``.agents/testing.md`` "The Real-Home Guard".

Every tree Coffer keeps — the vault with its knowledge and skill masters,
``local/``, ``content/``, ``derived/`` with the memory tree — resolves from
``HOME`` at the moment it is asked for, with no per-tree override (ADR
storage-is-five-classes-by-nature), so the fresh ``HOME`` each test gets from
``_real_home_guard`` below is what isolates every one of them.

The log directory is set at import time — not in a fixture — because
conftest.py is imported before any test module, and some modules call
``configure_logging()`` at import or app-construction time.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from tests.support import real_home_guard

#: This process's own scratch root. Everything the run needs outside a test's
#: ``tmp_path`` — the throwaway ``HOME`` and the log directory below — lives
#: under it, so two pytest processes (xdist workers, a nested pytest, a
#: second session's run) never share a directory or a log file.
_RUN_ROOT = Path(tempfile.mkdtemp(prefix="coffer-test-run-"))

_GUARD = real_home_guard.install(_RUN_ROOT / "home")

import pytest  # noqa: E402

from tests.support import hypothesis_profiles  # noqa: E402

hypothesis_profiles.register()

#: The isolated-HOME builders as fixtures (``isolated_home``, ``two_homes``,
#: ``claude_code_dir``, ``codex_dir``, ``fake_channel_adapter``).
pytest_plugins = ["tests.support.fixtures"]

_TEST_LOG_DIR = _RUN_ROOT / "logs"
os.environ.setdefault("COFFER_LOG_DIR", str(_TEST_LOG_DIR))

# Nearly every integration test boots the app, and the lifespan supervises the
# local model proxy — which would spawn a real subprocess per test. The tests
# of the proxy and its supervisor build their own; everything else runs
# without one (``surfaces/http/model_proxy_wiring.AUTOSTART_ENV``).
os.environ.setdefault("COFFER_MODEL_PROXY", "off")
# The daily price-list refresh fetches genai-prices over the network
# (``infrastructure/usage/price_refresh.REFRESH_ENV``); tests price from the
# snapshot in the tree.
os.environ.setdefault("COFFER_PRICE_REFRESH", "off")
# Every experimental feature is off until switched on, and almost every test
# drives routes, tools or passes of one of them, so the suite pins all four on
# (``COFFER_FEATURES``). The tests of the feature mechanism itself, and the
# gate tests of each feature's off state, replace the pin with
# ``tests.support.features.pin_features`` / ``monkeypatch``.
os.environ.setdefault("COFFER_FEATURES", "knowledge=on,memory=on,sync=on,models=on")


@pytest.fixture(autouse=True)
def _real_home_guard(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Give every test its own ``$HOME`` — and with it its own vault, knowledge,
    skill, memory, media and cache trees — and fail it if it touched the real one.

    Declared first so it is set up before, and torn down after, every other
    autouse fixture — their setup and teardown are inside the check. The home
    comes from ``tmp_path_factory``, not ``tmp_path``, so a test that lists its
    own ``tmp_path`` finds nothing it did not put there. A test that wants a
    particular home still sets ``HOME`` itself; its monkeypatch wins.
    """
    home = real_home_guard.write_home_skeleton(tmp_path_factory.mktemp("home"))
    monkeypatch.setenv("HOME", str(home))
    stray = _GUARD.drain()  # left by collection or a session fixture
    yield
    caught = stray + _GUARD.drain()
    if caught:
        pytest.fail(
            "touched the real home (see tests/support/real_home_guard.py):\n  "
            + "\n  ".join(str(v) for v in caught),
            pytrace=False,
        )


@pytest.fixture(autouse=True)
def _no_channel_burst_window(monkeypatch):
    """Release a channel message as soon as the loop turns instead of after the
    channel's quiet window (spec channels "Take a burst of messages as one turn"),
    so the suite does not sleep through it on every turn. A test about the window
    itself raises the cap again."""
    from coffer.application.channel import inbound_burst

    monkeypatch.setattr(inbound_burst, "MAX_WINDOW_SECONDS", 0.0)


@pytest.fixture(autouse=True)
def _restore_feature_service() -> Iterator[None]:
    """``create_app`` publishes the feature service process-wide, and a bare app
    in a later test reads it (``kind_enabled``): without this, whichever app an
    earlier test on the worker booted decides which features a test of a bare app
    sees."""
    from coffer.surfaces.http import feature_dependencies

    prior = feature_dependencies._feature_service
    yield
    feature_dependencies._feature_service = prior


# Accept any Host header across the suite. The loopback-Host guard
# (``coffer.surfaces.http.host_guard``) exists to stop a DNS-rebound *browser*
# page from reading the daemon's responses; these tests drive the ASGI app
# in-process over httpx/TestClient, where there is no network, no browser and
# therefore no rebinding — but where the transports do send made-up
# authorities like ``testserver``. The guard's own tests clear this variable
# and assert both directions for real.
os.environ.setdefault("COFFER_ALLOWED_HOSTS", "*")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """A violation outside any test (a session fixture's teardown, an import
    after the last test) still fails the run."""
    stray = _GUARD.drain()
    if stray:
        print("\nreal-home guard: touched outside any test:\n  " + "\n  ".join(map(str, stray)))
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
