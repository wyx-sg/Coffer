"""Tests for scripts/check_pyinstaller_specs.py.

The gate must see `datas=datas` (a variable assigned earlier in the spec), the
shape the daemon spec uses, not only a literal `datas=[...]`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_pyinstaller_specs.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_pyinstaller_specs", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_literal_and_variable_datas_are_both_read(tmp_path: Path) -> None:
    gate = _load()
    spec = tmp_path / "x.spec"
    spec.write_text(
        'datas = collect_data_files("a") + [("missing/dir", "dest")]\n'
        'datas = datas + [(_dist, "webui")]\n'
        'a = Analysis(["entry.py"], datas=datas, binaries=[("bin/x", ".")])\n'
    )
    assert gate.declared_paths(spec) == ["entry.py", "missing/dir", "bin/x"]


def test_real_daemon_spec_datas_are_resolved() -> None:
    gate = _load()
    paths = gate.declared_paths(REPO_ROOT / "backend" / "coffer-daemon.spec")
    assert "coffer/infrastructure/usage/price_list" in paths
    assert "coffer/application/knowledge/skill_assets" in paths


def test_utf8_option_detected(tmp_path: Path) -> None:
    gate = _load()
    good = tmp_path / "g.spec"
    good.write_text('exe = EXE(pyz, [("X utf8", None, "OPTION")])\n')
    bad = tmp_path / "b.spec"
    bad.write_text("exe = EXE(pyz, [])\n")
    assert gate.freezes_utf8_mode(good) is True
    assert gate.freezes_utf8_mode(bad) is False
