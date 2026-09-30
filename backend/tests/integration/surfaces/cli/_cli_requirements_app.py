"""A real ``create_app`` daemon whose required-command check runs against
fakes (``tests.support.cli_requirements``) — or against the real probe on a
``PATH`` the test lays out — and never against a real Homebrew."""

from __future__ import annotations

import pathlib
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from starlette.testclient import TestClient

from coffer.application.skill.cli_requirements import CommandProbePort
from coffer.surfaces.http import cli_wiring
from tests.support.cli_requirements import FakeCommandProbe, FakeInstaller

from ._real_app import boot


@dataclass
class CliDaemon:
    client: TestClient
    probe: CommandProbePort
    installer: FakeInstaller
    root: pathlib.Path

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

    def wait_install(self, command: str, timeout: float = 10.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            r = self.client.get(f"/clis/{command}/install")
            assert r.status_code == 200, r.text
            body: dict[str, Any] = r.json()
            if body["state"] != "running" or time.monotonic() > deadline:
                return body
            time.sleep(0.02)


def boot_cli_daemon(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    probe: CommandProbePort | None = None,
    installer: FakeInstaller | None = None,
) -> Iterator[CliDaemon]:
    fake_probe: CommandProbePort = probe or FakeCommandProbe()
    fake_installer = installer or FakeInstaller()
    build_probe: Callable[[], CommandProbePort] = lambda: fake_probe  # noqa: E731
    monkeypatch.setattr(cli_wiring, "build_command_probe", build_probe)
    monkeypatch.setattr(cli_wiring, "build_installer", lambda: fake_installer)
    for client in boot(tmp_path, monkeypatch):
        yield CliDaemon(client, fake_probe, fake_installer, tmp_path)
