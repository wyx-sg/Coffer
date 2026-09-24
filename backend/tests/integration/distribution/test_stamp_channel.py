"""``scripts/stamp_channel.py`` and the release workflow step that runs it.

The script is run against a copy of ``build_channel.py`` in ``tmp_path``: the
real module must stay ``dev`` in the tree.
"""

from __future__ import annotations

import importlib.util
import runpy
import shutil
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from coffer import build_channel

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPT = _REPO_ROOT / "scripts" / "stamp_channel.py"
_RELEASE = _REPO_ROOT / ".github" / "workflows" / "release.yml"


def _script() -> dict[str, object]:
    return runpy.run_path(str(_SCRIPT))


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("stamped_build_channel", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    target = tmp_path / "build_channel.py"
    shutil.copy(build_channel.__file__, target)
    return target


@pytest.mark.acceptance(
    spec="experimental-features", scenario="the release workflow stamps the stable channel"
)
def test_stamping_stable_makes_the_build_channel_stable(copy: Path) -> None:
    main = _script()["main"]
    assert main(["stable"], target=copy) == 0  # type: ignore[operator]
    assert _load(copy).CHANNEL == "stable"


def test_stamping_dev_again_restores_dev(copy: Path) -> None:
    main = _script()["main"]
    main(["stable"], target=copy)  # type: ignore[operator]
    main(["dev"], target=copy)  # type: ignore[operator]
    assert _load(copy).CHANNEL == "dev"
    assert copy.read_text() == Path(build_channel.__file__).read_text()


def test_an_unknown_channel_is_refused(copy: Path) -> None:
    main = _script()["main"]
    with pytest.raises(SystemExit):
        main(["beta"], target=copy)  # type: ignore[operator]
    assert _load(copy).CHANNEL == "dev"


def test_a_file_without_the_anchor_is_refused() -> None:
    stamp = _script()["stamp"]
    with pytest.raises(SystemExit):
        stamp("CHANNEL = 'dev'\n", "stable")  # type: ignore[operator]


def test_the_release_workflow_stamps_stable_before_building_binaries() -> None:
    steps = yaml.safe_load(_RELEASE.read_text())["jobs"]["bundle"]["steps"]
    runs = [str(step.get("run", "")) for step in steps]
    stamp_at = next(i for i, run in enumerate(runs) if "stamp_channel.py stable" in run)
    build_at = next(i for i, run in enumerate(runs) if "build_binaries.sh" in run)
    assert stamp_at < build_at
    assert "refs/tags/v" in str(steps[stamp_at].get("if", ""))
