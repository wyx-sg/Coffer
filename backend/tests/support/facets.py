"""The agent catalogue for tests: every facet bound the way the composition
root binds it, with the dependency probe replaced by a fixed answer.

The real probe looks for ``claude`` / ``codex`` on the machine's ``PATH``, so a
test that used it would pass or fail with what the developer happens to have
installed. :func:`agent_catalog` answers "not installed" for every program
unless the test says otherwise.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import stat
from collections.abc import Mapping

import pytest

from coffer.domain.agent.detection import ProgramInfo
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.types import AgentType
from coffer.surfaces.http.agent_facet_wiring import build_agent_catalog


@dataclasses.dataclass
class FixedProbe:
    """``DependencyProbe`` with a fixed answer; counts its calls."""

    program: str
    info: ProgramInfo = dataclasses.field(default_factory=ProgramInfo)
    calls: int = 0

    def probe(self) -> ProgramInfo:
        self.calls += 1
        return self.info


def installed(version: str = "1.0.0", path: str = "/usr/local/bin/agent") -> ProgramInfo:
    return ProgramInfo(path=path, version=version)


#: The ``coffer`` CLI the delivery hooks run in tests. Fixed, so an installed
#: command never depends on what the developer's own ``PATH`` holds.
TEST_COFFER_CLI = "/opt/coffer/bin/coffer"


def agent_catalog(programs: Mapping[AgentType, ProgramInfo] | None = None) -> AgentCatalog:
    """The production catalogue, each probe answering from ``programs``, and
    the delivery hooks running :data:`TEST_COFFER_CLI`."""
    found = dict(programs or {})
    return AgentCatalog(
        {
            d.type: dataclasses.replace(
                d, dependency_probe=FixedProbe(d.program, found.get(d.type, ProgramInfo()))
            )
            for d in build_agent_catalog(coffer_cli=TEST_COFFER_CLI)
        }
    )


def put_programs_on_path(
    monkeypatch: pytest.MonkeyPatch, bin_dir: pathlib.Path, versions: Mapping[str, str]
) -> pathlib.Path:
    """Executables named after ``versions``' keys, each printing its value for
    ``--version``, on the front of this process's ``PATH`` — for tests that go
    through the real dependency probe (the app, the CLI against a daemon).

    The probe also reads the login shell's ``PATH``, so on a machine that has
    the real program the real one may be found first: assert the state, which
    is the same either way, not the version."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, output in versions.items():
        path = bin_dir / name
        path.write_text(f'#!/bin/sh\necho "{output}"\n', encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]))
    return bin_dir


__all__ = ["TEST_COFFER_CLI", "FixedProbe", "agent_catalog", "installed", "put_programs_on_path"]
