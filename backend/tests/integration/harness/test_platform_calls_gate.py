"""Tests for scripts/check_platform_calls.py — the operating-system check gate.

The gate fails on an OS check (``sys.platform``, ``platform.system()``,
``os.name`` …) anywhere in ``backend/coffer/`` outside
``infrastructure/platform/``. Each rule is proved to bite on synthetic source
and to stay quiet on code that only looks similar; the real tree is proved
clean, and the allowed package is proved exempt.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_platform_calls.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_platform_calls", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_platform_calls"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('import sys\nif sys.platform == "win32":\n    pass\n', "sys.platform"),
        ('import sys\nok = sys.platform.startswith("linux")\n', "sys.platform"),
        ("import platform\nname = platform.system()\n", "platform.system()"),
        ("import platform\nv = platform.mac_ver()\n", "platform.mac_ver()"),
        ("import platform\nr = platform.release()\n", "platform.release()"),
        ('import os\nwin = os.name == "nt"\n', "os.name"),
        ("import os\nu = os.uname()\n", "os.uname"),
        ("import sys as _s\nx = _s.platform\n", "sys.platform"),
        ("import platform as p\nx = p.system()\n", "platform.system()"),
        ("from sys import platform\n", "from sys import platform"),
        ("from os import name\n", "from os import name"),
        ("from platform import system\n", "from platform import system"),
    ],
)
def test_each_os_check_is_caught(gate: ModuleType, source: str, expected: str) -> None:
    hits = gate.scan_source(source)
    assert [what for _line, what in hits] == [expected]


@pytest.mark.parametrize(
    "source",
    [
        # A parameter or attribute that happens to be called `platform`.
        "def f(platform):\n    return platform.os_label()\n",
        "class A:\n    def g(self):\n        return self._platform.system()\n",
        # Other attributes of the same modules.
        "import sys\nexe = sys.executable\n",
        "import os\nsep = os.sep\npath = os.path.join('a', 'b')\n",
        "import platform\nimpl = platform.python_implementation()\n",
        # A string that merely mentions it.
        's = "sys.platform"\n',
    ],
)
def test_lookalikes_are_not_caught(gate: ModuleType, source: str) -> None:
    assert gate.scan_source(source) == []


def test_line_numbers_point_at_the_check(gate: ModuleType) -> None:
    source = 'import sys\n\n\nif sys.platform == "darwin":\n    pass\n'
    assert gate.scan_source(source) == [(4, "sys.platform")]


def test_the_platform_package_is_exempt_and_nothing_else(
    gate: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg = tmp_path / "coffer"
    allowed = pkg / "infrastructure" / "platform"
    allowed.mkdir(parents=True)
    (allowed / "host.py").write_text("import sys\nX = sys.platform\n", encoding="utf-8")
    app = pkg / "application"
    app.mkdir()
    (app / "svc.py").write_text("import sys\nX = sys.platform\n", encoding="utf-8")
    # A sibling whose name merely starts with "platform" is not exempt.
    (pkg / "infrastructure" / "platform_extra.py").write_text(
        "import os\nX = os.name\n", encoding="utf-8"
    )
    monkeypatch.setattr(gate, "ALLOWED", allowed)

    found = gate.scan_tree(pkg)

    assert sorted((p.name, what) for p, _line, what in found) == [
        ("platform_extra.py", "os.name"),
        ("svc.py", "sys.platform"),
    ]


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
