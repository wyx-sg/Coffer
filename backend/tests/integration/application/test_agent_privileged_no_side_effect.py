"""A privileged config dir is refused before anything is created under it.

spec agent-registry "Validate the config directory at registration": the
privileged-path defence rejects the directory — it must not first ``mkdir`` the
``skills`` leaf inside a system location and only then object to it.

The privileged prefix set is pointed at a tmp dir so the test can observe the
filesystem; the ``/var/folders`` carve-out is dropped because pytest's tmp dirs
live under it on macOS.
"""

from __future__ import annotations

import pytest

import coffer.application.agent.service as agent_service_mod
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import PrivilegedPath


def _privilege(monkeypatch, root) -> None:
    resolved = str(root.resolve())
    monkeypatch.setattr(agent_service_mod, "_PRIVILEGED_PREFIXES_POSIX", (resolved,))
    monkeypatch.setattr(agent_service_mod, "_PRIVILEGED_CARVE_OUTS_POSIX", ())


async def test_register_into_privileged_dir_creates_nothing(agent_bundle, tmp_path, monkeypatch):
    system = tmp_path / "system"
    config_dir = system / ".codex"
    config_dir.mkdir(parents=True)
    _privilege(monkeypatch, system)

    with pytest.raises(PrivilegedPath):
        await agent_bundle.svc.register(
            agent_type=AgentType.CODEX, name="sys", config_dir=str(config_dir), actor="cli"
        )

    assert not (config_dir / "skills").exists()
    assert list(config_dir.iterdir()) == []
    assert await agent_bundle.svc.list() == []


async def test_update_into_privileged_dir_creates_nothing(agent_bundle, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    agent = await agent_bundle.svc.register(
        agent_type=AgentType.CODEX, name="a", config_dir=str(home), actor="cli"
    )
    system = tmp_path / "system"
    config_dir = system / ".codex"
    config_dir.mkdir(parents=True)
    _privilege(monkeypatch, system)

    with pytest.raises(PrivilegedPath):
        await agent_bundle.svc.update_config_dir(
            uid=agent.uid, new_config_dir=str(config_dir), actor="cli"
        )

    assert list(config_dir.iterdir()) == []
    assert (await agent_bundle.svc.get(agent.uid)).config["config_dir"] == str(home)
