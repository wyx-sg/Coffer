"""Tests for scripts/check_bare_tasks.py — no background task outside the supervisor.

The gate counts ``create_task`` / ``ensure_future`` calls per file under
``backend/coffer/`` and fails when a file makes more than its allow-list entry,
or fewer (a stale entry). Proved on a synthetic package, then on the real tree.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_bare_tasks.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_bare_tasks", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_bare_tasks"] = mod
    spec.loader.exec_module(mod)
    return mod


def _package(root: Path, files: dict[str, str]) -> Path:
    for rel, source in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return root


@pytest.mark.acceptance(spec="daemon", scenario="a new bare background task fails the lint gate")
def test_a_new_bare_task_fails_and_names_the_file(gate: ModuleType, tmp_path: Path) -> None:
    pkg = _package(
        tmp_path,
        {
            "application/channel/worker.py": (
                "import asyncio\n"
                "def start(loop_body):\n"
                "    return asyncio.create_task(loop_body())\n"
            ),
            "application/runtime/supervisor.py": (
                "import asyncio\ndef spawn(c, *, name):\n"
                "    return asyncio.get_running_loop().create_task(c, name=name)\n"
            ),
        },
    )
    problems, _total = gate.check(pkg, allowed={})
    assert len(problems) == 1
    assert "application/channel/worker.py" in problems[0]
    assert "spawn()" in problems[0]


def test_every_call_form_is_counted(gate: ModuleType, tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "from asyncio import ensure_future\n"
        "async def f(loop, work):\n"
        "    a = asyncio.create_task(work())\n"
        "    b = loop.create_task(work())\n"
        "    c = asyncio.ensure_future(work())\n"
        "    d = ensure_future(work())\n"
    )
    path = tmp_path / "m.py"
    path.write_text(source)
    assert gate.count_calls(path) == 4


def test_an_allow_listed_file_passes_and_a_stale_entry_fails(
    gate: ModuleType, tmp_path: Path
) -> None:
    pkg = _package(
        tmp_path,
        {
            "surfaces/race.py": (
                "import asyncio\n"
                "async def race(q, stop):\n"
                "    a = asyncio.ensure_future(q.get())\n"
                "    b = asyncio.ensure_future(stop.wait())\n"
                "    await asyncio.wait({a, b})\n"
            ),
        },
    )
    ok, total = gate.check(pkg, allowed={"surfaces/race.py": (2, "a race awaited in place")})
    assert ok == [] and total == 2
    stale, _ = gate.check(pkg, allowed={"surfaces/race.py": (3, "a race awaited in place")})
    assert len(stale) == 1 and "lower its entry" in stale[0]


def test_the_real_tree_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
