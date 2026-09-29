"""Root test configuration.

First, before anything imports ``coffer``: the real-home guard
(``tests/support/real_home_guard.py``). ``HOME`` is pointed at a throwaway
directory, every ``COFFER_*`` variable inherited from the developer's shell is
stripped, and an audit hook refuses — and records — any filesystem, SQLite or
spawn event under the real home's ``.coffer`` / agent config trees. A test that
trips it fails in teardown even when the code under test swallowed the
``PermissionError``. See ``.agents/testing.md`` "The Real-Home Guard".

Then the per-root pins below. With ``HOME`` redirected they are no longer the
only thing between a test and the live vault, but they still give each tree
its own directory, and the autouse fixtures below make that per test.

These are set at import time — not in a fixture — because conftest.py is
imported before any test module, and some modules call ``configure_logging()``
at import or app-construction time.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from tests.support import real_home_guard

#: This process's own scratch root. Everything the run needs outside a test's
#: ``tmp_path`` — the throwaway ``HOME`` and the four per-root defaults below —
#: lives under it, so two pytest processes (xdist workers, a nested pytest, a
#: second session's run) never share a directory or a log file.
_RUN_ROOT = Path(tempfile.mkdtemp(prefix="coffer-test-run-"))

_GUARD = real_home_guard.install(_RUN_ROOT / "home")

import pytest  # noqa: E402

#: The isolated-HOME builders as fixtures (``isolated_home``, ``two_homes``,
#: ``claude_code_dir``, ``codex_dir``, ``fake_channel_adapter``).
pytest_plugins = ["tests.support.fixtures"]

_TEST_LOG_DIR = _RUN_ROOT / "logs"
os.environ.setdefault("COFFER_LOG_DIR", str(_TEST_LOG_DIR))

# Same reason, and a far worse failure mode: ``paths.knowledge_root()`` falls
# back to ``$HOME/.coffer/knowledge`` when ``COFFER_KNOWLEDGE_ROOT`` is unset,
# so any test that boots the app without pinning it runs the knowledge
# migration over the developer's REAL vault — moving their files, not just
# writing a log line. Pinned at import time so no test can reach the live tree
# by forgetting a fixture; a test that wants its own tree overrides it per-test
# with monkeypatch, which takes precedence over this default.
_TEST_KNOWLEDGE_ROOT = _RUN_ROOT / "knowledge"
os.environ.setdefault("COFFER_KNOWLEDGE_ROOT", str(_TEST_KNOWLEDGE_ROOT))

# Same failure mode again, one layer over: ``paths.memory_root()`` (spec
# memory) falls back to ``$HOME/.coffer/memory`` when ``COFFER_MEMORY_ROOT``
# is unset, and that tree is a developer's real aggregated memory — a test
# that forgets to pin this would delete and rewrite it, not just pollute a log.
_TEST_MEMORY_ROOT = _RUN_ROOT / "memory"
os.environ.setdefault("COFFER_MEMORY_ROOT", str(_TEST_MEMORY_ROOT))

# And once more for the agent layer's own derived state (the transcript
# summary sidecar): ``paths.agent_state_root()`` falls back to
# ``$HOME/.coffer/cache/agent``. Nothing under it is a truth — deleting it
# only costs a slow listing — but a test run has no business writing into the
# developer's ``~/.coffer`` at all, and a sidecar shared between tests would
# hand one test the summaries another test's tree left behind.
_TEST_AGENT_STATE_ROOT = _RUN_ROOT / "agent-state"
os.environ.setdefault("COFFER_AGENT_STATE_ROOT", str(_TEST_AGENT_STATE_ROOT))

# Nearly every integration test boots the app, and the lifespan supervises the
# local model proxy — which would spawn a real subprocess per test. The tests
# of the proxy and its supervisor build their own; everything else runs
# without one (``surfaces/http/model_proxy_wiring.AUTOSTART_ENV``).
os.environ.setdefault("COFFER_MODEL_PROXY", "off")


@pytest.fixture(autouse=True)
def _real_home_guard(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Give every test its own ``$HOME`` and fail it if it touched the real one.

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


@pytest.fixture(autouse=True)
def _isolated_memory_root(tmp_path, monkeypatch):
    """Give every test its own memory tree, for the same reason as knowledge's."""
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory-root"))


@pytest.fixture(autouse=True)
def _isolated_agent_state_root(tmp_path, monkeypatch):
    """Give every test its own transcript sidecar.

    Isolation, not just safety: the sidecar is keyed by absolute path, and two
    tests that both build a transcript tree under their own ``tmp_path`` would
    otherwise share one file — so a test asserting "a cold reader parses every
    file" would find another test's entries already sitting in it.
    """
    monkeypatch.setenv("COFFER_AGENT_STATE_ROOT", str(tmp_path / "agent-state"))


@pytest.fixture(autouse=True)
def _no_channel_burst_window(monkeypatch):
    """Release a channel message as soon as the loop turns instead of after the
    channel's quiet window (spec channels "Take a burst of messages as one turn"),
    so the suite does not sleep through it on every turn. A test about the window
    itself raises the cap again."""
    from coffer.application.channel import inbound_burst

    monkeypatch.setattr(inbound_burst, "MAX_WINDOW_SECONDS", 0.0)


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
