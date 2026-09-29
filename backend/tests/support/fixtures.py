"""Suite-wide fixtures over the isolated-HOME builders.

Loaded by the root conftest (``pytest_plugins``), so every tier can request
them by name without importing anything:

* ``isolated_home`` — one machine, already active in this process.
* ``two_homes`` — two machines and a bare remote; neither is active.
* ``claude_code_dir`` / ``codex_dir`` — that agent's default config tree in
  ``isolated_home``.
* ``fake_channel_adapter`` — a fresh recording IM transport.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.agent.types import AgentType
from tests.support.channel import FakeChannelAdapter
from tests.support.homes import (
    FakeAgentDir,
    IsolatedHome,
    TwoMachineHomes,
    fake_agent_dir,
    make_home,
    two_machine_homes,
)


@pytest.fixture
def isolated_home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> IsolatedHome:
    return make_home(tmp_path / "home").activate(monkeypatch)


@pytest.fixture
def two_homes(tmp_path: pathlib.Path) -> TwoMachineHomes:
    return two_machine_homes(tmp_path / "fleet")


@pytest.fixture
def claude_code_dir(isolated_home: IsolatedHome) -> FakeAgentDir:
    return fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE)


@pytest.fixture
def codex_dir(isolated_home: IsolatedHome) -> FakeAgentDir:
    return fake_agent_dir(isolated_home, AgentType.CODEX)


@pytest.fixture
def fake_channel_adapter() -> FakeChannelAdapter:
    return FakeChannelAdapter()
