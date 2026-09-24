"""``CodexRpcModelDiscovery`` asks the Codex whose home is the agent's config dir.

``model/list`` answers for the account and config of whichever ``CODEX_HOME``
the app-server starts under. An agent registered with its own directory is
asked in that directory; the default one inherits the daemon's environment.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from coffer.infrastructure.agent.codex_rpc_models import CodexRpcModelDiscovery
from tests.unit.infrastructure.agent.test_codex_rpc_models import (
    FakeCodexPeer,
    _FakeSession,
    _model,
)


def _recording_factory(peer: FakeCodexPeer) -> tuple[Any, list[dict[str, str] | None]]:
    envs: list[dict[str, str] | None] = []

    def make(cwd: str, env: dict[str, str] | None) -> _FakeSession:
        envs.append(env)
        return _FakeSession(peer, cwd)

    return make, envs


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="ask model/list of the agent's own Codex home"
)
async def test_a_custom_config_dir_is_probed_under_its_own_codex_home(home: pathlib.Path) -> None:
    custom = home / "work-codex"
    custom.mkdir()
    peer = FakeCodexPeer([{"data": [_model("gpt-x")], "nextCursor": None}])
    make, envs = _recording_factory(peer)

    await CodexRpcModelDiscovery(make).discover(agent_key="codex", config_dir=custom)

    env = envs[0]
    assert env is not None
    assert env["CODEX_HOME"] == str(custom)
    assert "PATH" in env  # merged with the daemon env, not replacing it


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="ask model/list of the agent's own Codex home"
)
async def test_the_default_config_dir_inherits_the_daemon_env(home: pathlib.Path) -> None:
    default = home / ".codex"
    default.mkdir()
    peer = FakeCodexPeer([{"data": [_model("gpt-x")], "nextCursor": None}])
    make, envs = _recording_factory(peer)

    await CodexRpcModelDiscovery(make).discover(agent_key="codex", config_dir=default)

    assert envs == [None]


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="ask model/list of the agent's own Codex home"
)
async def test_two_config_dirs_are_not_answered_from_one_cache(home: pathlib.Path) -> None:
    """Two homes can be two accounts: the cached answer for one must not be
    served for the other."""
    custom = home / "work-codex"
    custom.mkdir()
    peer = FakeCodexPeer([{"data": [_model("gpt-x")], "nextCursor": None}])
    make, envs = _recording_factory(peer)
    discovery = CodexRpcModelDiscovery(make)

    await discovery.discover(agent_key="codex", config_dir=home / ".codex")
    await discovery.discover(agent_key="codex", config_dir=custom)

    assert len(envs) == 2
