"""The real-home guard fires, and blocks, when a test reaches the real home.

Every probe here aims at a name that does not exist under the real home
(``.s0-guard-probe-<uuid>``), so even a broken guard could only ever create one
stray empty entry — never overwrite, move or delete anything the developer has.
The asserts that the entry is still absent afterwards are what prove the guard
refused *before* the syscall, not after it.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import uuid

import pytest

from coffer.infrastructure.knowledge import paths as knowledge_paths
from tests.support import real_home_guard
from tests.support.real_home_guard import RealHomeAccessError, RealHomeGuard

BACKEND = pathlib.Path(__file__).resolve().parents[3]


def _guard() -> RealHomeGuard:
    assert real_home_guard.GUARD is not None, "the root conftest did not install the guard"
    return real_home_guard.GUARD


def _real_home() -> pathlib.Path:
    import pwd

    return pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir)


def _probe(under: str = ".coffer") -> pathlib.Path:
    return _real_home() / under / f".s0-guard-probe-{uuid.uuid4().hex}"


def test_home_is_redirected_away_from_the_real_one() -> None:
    home = os.environ["HOME"]
    assert pathlib.Path.home() == pathlib.Path(home)
    assert os.path.abspath(home) not in _guard().homes
    assert _guard().protected_root(os.path.join(home, ".coffer", "coffer.db")) is None
    # Only the suite's own pins survive: a COFFER_* the developer's shell
    # exported (a DB URL, a log directory) was stripped at import.
    pins = {
        "COFFER_LOG_DIR",
        "COFFER_ALLOWED_HOSTS",
        # The root conftest keeps the app from spawning the model proxy and a
        # background ``codex app-server`` in every test that boots it.
        "COFFER_MODEL_PROXY",
        "COFFER_QUOTA_POLL",
        # ... and from fetching the model price list over the network.
        "COFFER_PRICE_REFRESH",
        real_home_guard.REAL_HOME_ENV,
    }
    leaked = {
        k
        for k in os.environ
        if k.startswith("COFFER_")
        and k not in pins
        and not k.startswith(("COFFER_RUN_", "COFFER_SMOKE_"))
    }
    assert leaked == set()
    assert "CLAUDE_CONFIG_DIR" not in os.environ and "CODEX_HOME" not in os.environ


@pytest.mark.parametrize("under", [".coffer", ".claude", ".codex"])
def test_writing_under_the_real_home_is_refused_before_it_happens(under: str) -> None:
    probe = _probe(under)
    with _guard().expect_violation() as caught, pytest.raises(RealHomeAccessError):
        probe.write_text("must never land", encoding="utf-8")
    assert not probe.exists()
    assert [v.event for v in caught] == ["open"]
    assert str(probe) in caught[0].detail


def test_the_knowledge_root_incident_is_caught() -> None:
    """The original bug: with ``HOME`` gone, ``knowledge_root()`` resolves
    into the real vault, and the migration then creates directories there."""
    mp = pytest.MonkeyPatch()
    try:
        mp.delenv("HOME", raising=False)
        root = knowledge_paths.knowledge_root()
    finally:
        mp.undo()
    assert root == _real_home() / ".coffer" / "vault" / "knowledge"
    target = root / f".s0-guard-probe-{uuid.uuid4().hex}"
    with _guard().expect_violation() as caught, pytest.raises(RealHomeAccessError):
        target.mkdir(parents=True)
    assert not target.exists()
    assert caught and caught[0].event == "os.mkdir"


def test_sqlite_listing_and_tree_removal_are_refused() -> None:
    probe = _probe()
    with _guard().expect_violation() as caught:
        with pytest.raises(RealHomeAccessError):
            sqlite3.connect(probe)
        with pytest.raises(RealHomeAccessError):
            os.listdir(_real_home() / ".coffer")
        with pytest.raises(RealHomeAccessError):
            shutil.rmtree(probe)
    assert not probe.exists()
    assert [v.event for v in caught] == ["sqlite3.connect", "os.listdir", "shutil.rmtree"]


def test_a_spawned_process_inherits_the_isolated_home() -> None:
    out = subprocess.run(
        [sys.executable, "-c", "import pathlib; print(pathlib.Path.home())"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert out == os.environ["HOME"]
    assert out not in _guard().homes


def test_the_run_wide_log_dir_belongs_to_this_process_alone() -> None:
    """Under xdist every worker is its own pytest process. The log dir is the
    one pin no fixture narrows per test, so it must sit in this process's
    scratch root — not in a fixed ``/tmp`` name every worker (and every other
    session's run) appends to and rotates at once."""
    run_root = pathlib.Path(os.environ["COFFER_LOG_DIR"]).parent
    assert run_root.name.startswith("coffer-test-run-")
    assert run_root.parent == pathlib.Path(tempfile.gettempdir())


@pytest.mark.parametrize("env_home", [None, "real"])
def test_spawning_with_no_home_or_the_real_home_is_refused(env_home: str | None) -> None:
    env = {"PATH": os.environ.get("PATH", "")}
    if env_home == "real":
        env["HOME"] = str(_real_home())
    with _guard().expect_violation() as caught, pytest.raises(RealHomeAccessError):
        subprocess.run([sys.executable, "-c", "pass"], env=env, check=True)
    assert [v.event for v in caught] == ["subprocess.Popen"]
    assert ("no HOME" if env_home is None else "the real home") in caught[0].detail


def test_a_swallowed_refusal_still_fails_the_test(tmp_path: pathlib.Path) -> None:
    """Code that tolerates an unreadable file would eat the PermissionError; the
    recorded violation must fail the test anyway. Proven on a nested run that
    loads the real root conftest."""
    probe = _probe()
    (tmp_path / "conftest.py").write_text(
        "from tests.conftest import _real_home_guard, pytest_sessionfinish  # noqa: F401\n"
    )
    (tmp_path / "test_swallows.py").write_text(
        textwrap.dedent(
            f"""
            def test_swallows():
                try:
                    open({str(probe)!r}, "w")
                except OSError:
                    pass
            """
        )
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        timeout=120,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "touched the real home" in proc.stdout
    assert str(probe) in proc.stdout
    assert not probe.exists()
