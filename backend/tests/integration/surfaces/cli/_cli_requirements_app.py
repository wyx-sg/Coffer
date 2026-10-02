"""A real ``create_app`` daemon whose required-command check runs against a
fake probe (``tests.support.cli_requirements``) — or against the real probe on
a ``PATH`` the test lays out — on a machine described as
:data:`~tests.support.cli_requirements.FAKE_MACHINE`."""

from __future__ import annotations

import pathlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from starlette.testclient import TestClient

from coffer.application.skill.cli_requirements import CommandProbePort
from coffer.surfaces.http import cli_wiring
from tests.support.cli_requirements import FAKE_MACHINE, FakeCommandProbe, FakeHelpRunner

from ._real_app import boot


@dataclass
class CliDaemon:
    client: TestClient
    probe: CommandProbePort
    root: pathlib.Path
    help_runner: FakeHelpRunner

    def add_skill(self, name: str, requires: str) -> str:
        """Import a skill whose SKILL.md declares ``requires`` (YAML list
        lines, already indented); returns its uid."""
        folder = self.root / "src" / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: A test skill.\nrequires:\n{requires}---\n# {name}\n",
            encoding="utf-8",
        )
        r = self.client.post("/skills/import", json={"path": str(folder)})
        assert r.status_code == 201, r.text
        return str(r.json()["uid"])


def boot_cli_daemon(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    probe: CommandProbePort | None = None,
    help_runner: FakeHelpRunner | None = None,
) -> Iterator[CliDaemon]:
    fake_probe: CommandProbePort = probe or FakeCommandProbe()
    build_probe: Callable[[], CommandProbePort] = lambda: fake_probe  # noqa: E731
    runner = help_runner or FakeHelpRunner()
    monkeypatch.setattr(cli_wiring, "build_command_probe", build_probe)
    monkeypatch.setattr(cli_wiring, "build_help_runner", lambda: runner)
    monkeypatch.setattr(cli_wiring, "machine_label", lambda: FAKE_MACHINE)
    for client in boot(tmp_path, monkeypatch):
        yield CliDaemon(client, fake_probe, tmp_path, runner)
