"""How the daemon reaches a user's machine: the console scripts a source
install puts on ``PATH``, and the one checksum file a release publishes.

The checksum test runs the release workflow's own shell steps — extracted from
``.github/workflows/release.yml`` rather than restated here — over a staged
tree under ``tmp_path``, then verifies the result with a stock SHA-256 checker.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[4]


@pytest.mark.acceptance(
    spec="daemon", scenario="a source install puts the CLI and the shim on PATH"
)
def test_a_source_install_declares_both_console_scripts() -> None:
    pyproject = tomllib.loads((_REPO / "backend" / "pyproject.toml").read_text())
    scripts = pyproject["project"]["scripts"]
    assert {"coffer", "coffer-mcp-shim"} <= set(scripts)

    for name in ("coffer", "coffer-mcp-shim"):
        module_name, _, attr = scripts[name].partition(":")
        target = getattr(importlib.import_module(module_name), attr)
        assert callable(target), f"{name} must resolve to a callable entry point"

    # The installed distribution carries the same entry points, so pip wrote
    # the executables it names.
    installed = {
        ep.name: ep.value
        for ep in importlib.metadata.entry_points(group="console_scripts")
        if ep.name in {"coffer", "coffer-mcp-shim"}
    }
    assert installed == {name: scripts[name] for name in ("coffer", "coffer-mcp-shim")}


def _step_script(workflow: dict, job: str, step_name: str) -> str:
    for step in workflow["jobs"][job]["steps"]:
        if step.get("name") == step_name:
            return str(step["run"])
    raise AssertionError(f"release.yml job {job!r} has no step {step_name!r}")


def _checker() -> list[str]:
    if shutil.which("sha256sum"):
        return ["sha256sum", "-c", "SHA256SUMS"]
    return ["shasum", "-a", "256", "-c", "SHA256SUMS"]


@pytest.mark.skipif(shutil.which("bash") is None, reason="the workflow steps are bash")
@pytest.mark.acceptance(
    spec="daemon", scenario="one checksum file verifies every artifact of every leg"
)
def test_one_checksum_file_verifies_every_artifact_of_every_leg(tmp_path: Path) -> None:
    workflow = yaml.safe_load((_REPO / ".github" / "workflows" / "release.yml").read_text())
    per_leg = _step_script(workflow, "bundle", "compute SHA256SUMS")
    stage = _step_script(workflow, "release", "stage release assets")

    legs = {
        "coffer-aarch64": {
            "coffer-cli-aarch64-apple-darwin.tar.gz": b"cli archive bytes",
            "Coffer-unsigned-aarch64-apple-darwin.dmg": b"dmg bytes",
        },
        "coffer-other-leg": {"coffer-cli-other.tar.gz": b"another leg's archive"},
    }
    for leg, files in legs.items():
        leg_dir = tmp_path / "leg" / leg
        (leg_dir / "artifacts").mkdir(parents=True)
        for name, content in files.items():
            (leg_dir / "artifacts" / name).write_bytes(content)
        subprocess.run(["bash", "-c", per_leg], cwd=leg_dir, check=True, capture_output=True)
        # What `gh run download` lays out: one directory per uploaded artifact.
        shutil.copytree(leg_dir / "artifacts", tmp_path / "dist-artifacts" / leg)

    subprocess.run(["bash", "-c", stage], cwd=tmp_path, check=True, capture_output=True)

    release = tmp_path / "release"
    sums = list(release.rglob("SHA256SUMS"))
    assert sums == [release / "SHA256SUMS"], "the release must hold exactly one SHA256SUMS"

    staged = sorted(p.name for p in release.iterdir() if p.name != "SHA256SUMS")
    expected = sorted(name for files in legs.values() for name in files)
    assert staged == expected

    listed = [line.split()[-1] for line in (release / "SHA256SUMS").read_text().splitlines()]
    assert sorted(listed) == expected, "every artifact is listed exactly once"

    check = subprocess.run(_checker(), cwd=release, capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
    assert check.stdout.count(": OK") == len(expected)
