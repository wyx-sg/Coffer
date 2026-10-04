"""Tests for scripts/check_coffer_paths.py — the ``~/.coffer`` path gate.

The gate fails on a ``~/.coffer`` path built anywhere in ``backend/coffer/``
or ``backend/tests/support/`` outside ``infrastructure/vault/home.py`` and a
short allow-list. Each rule is proved to bite on synthetic source and to stay
quiet on prose that only names the path; the real tree is proved clean, and
the allow-list is proved exempt.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_coffer_paths.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_coffer_paths", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_coffer_paths"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('from pathlib import Path\np = Path.home() / ".coffer"\n', '".coffer"'),
        ('import os\np = os.path.join(os.environ["HOME"], ".coffer")\n', '".coffer"'),
        ('p = home / ".coffer/logs"\n', '".coffer/logs"'),
        (
            'from pathlib import Path\np = Path("~/.coffer/logs").expanduser()\n',
            'Path("~/.coffer/logs")',
        ),
        ('import os\np = os.path.expanduser("~/.coffer")\n', 'expanduser("~/.coffer")'),
        (
            'import pathlib\nurl = f"sqlite:///{pathlib.Path.home()}/.coffer/runs.db"\n',
            "an f-string joining /.coffer",
        ),
        ('from pathlib import Path\np = Path.home() / "vault"\n', 'Path.home() / "vault"'),
        (
            'import pathlib\np = pathlib.Path.home() / "daemon.json"\n',
            'Path.home() / "daemon.json"',
        ),
    ],
)
def test_each_construction_is_caught(gate: ModuleType, source: str, expected: str) -> None:
    hits = gate.scan_source(source)
    assert [what for _line, what in hits] == [expected]


@pytest.mark.parametrize(
    "source",
    [
        # Prose that names the path to a person.
        '"""Binaries land in ``~/.coffer/bin``."""\n',
        'msg = "run it from ~/.coffer/bin"\n',
        'typer.echo(f"see {name} under ~/.coffer/logs")\n',
        'Setting("daemon.port", "~/.coffer/daemon-config.json")\n',
        # A file name that merely starts with the word.
        'IGNORED = {".coffer.meta.json"}\n',
        # Path.home() joined to something that is not a Coffer entry.
        'from pathlib import Path\np = Path.home() / "Library" / "LaunchAgents"\n',
        # A Coffer entry joined to something other than the home.
        'p = root / "vault"\n',
    ],
)
def test_lookalikes_are_not_caught(gate: ModuleType, source: str) -> None:
    assert gate.scan_source(source) == []


def test_line_numbers_point_at_the_construction(gate: ModuleType) -> None:
    source = 'from pathlib import Path\n\n\np = Path.home() / ".coffer"\n'
    assert gate.scan_source(source) == [(4, '".coffer"')]


def test_the_allow_list_is_exempt_and_nothing_else(
    gate: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg = tmp_path / "coffer"
    home = pkg / "infrastructure" / "vault" / "home.py"
    migrations = pkg / "infrastructure" / "persistence" / "migrations"
    migrations.mkdir(parents=True)
    home.parent.mkdir(parents=True)
    body = 'from pathlib import Path\nP = Path.home() / ".coffer"\n'
    home.write_text(body, encoding="utf-8")
    (migrations / "m_0001.py").write_text(body, encoding="utf-8")
    (pkg / "infrastructure" / "vault" / "home_extra.py").write_text(body, encoding="utf-8")
    (pkg / "svc.py").write_text(body, encoding="utf-8")
    monkeypatch.setattr(gate, "ALLOWED", (home, migrations))

    found = gate.scan_tree((pkg,))

    assert sorted(p.name for p, _line, _what in found) == ["home_extra.py", "svc.py"]


def test_the_real_tree_is_clean() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout
