"""The vault upgrade turns a connection's ``is_active`` into the agents' own
``connection_uid`` (spec provider-switching data model, "Upgrade").

The old build kept one boolean per connection for every agent type it reached;
this build keeps the choice on each agent. Nothing at runtime reads the old
flag, so the conversion happens once, here, and the files it writes are ones the
current ``ProviderConfig`` and ``AgentConfig`` (both ``extra="forbid"``) accept.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.agent.config import AgentConfig
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.scope import Scope
from coffer.infrastructure.vault.migration.connection_choice import settle_connection_choice
from coffer.infrastructure.vault.migration.legacy_db import OldResource

_CLAUDE = "a" * 32
_CODEX = "b" * 32


def _agent(uid: str, agent_type: str, **extra: Any) -> OldResource:
    return OldResource(
        uid=uid,
        kind="agent",
        name=agent_type.replace("_", "-"),
        description=None,
        title=None,
        config={"type": agent_type, "config_dir": f"/tmp/{agent_type}", **extra},
        enabled=True,
        scope=None,
    )


def _connection(
    name: str,
    *,
    active: bool,
    scope: Scope | None = None,
    enabled: bool = True,
    protocol: str = "openai",
) -> OldResource:
    return OldResource(
        uid=(name * 32)[:32],
        kind="provider",
        name=name,
        description=None,
        title=None,
        config={
            "protocol": protocol,
            "base_url": "https://gw/v1",
            "secret_ref": None if protocol == "ollama" else "provider/x/key",
            "is_active": active,
        },
        enabled=enabled,
        scope=scope,
    )


def _settled(resources: list[OldResource]) -> dict[str, dict[str, Any]]:
    return {r.name: r.config for r in settle_connection_choice(resources)}


def test_an_active_connection_becomes_the_choice_of_every_agent_it_reached() -> None:
    claude, codex = _agent(_CLAUDE, "claude_code"), _agent(_CODEX, "codex")
    both = _connection("a", active=True)
    out = _settled([claude, codex, both])
    assert out["claude-code"]["connection_uid"] == both.uid
    assert out["codex"]["connection_uid"] == both.uid
    assert "is_active" not in out["a"]


def test_a_scope_that_names_one_agent_reaches_only_that_agent() -> None:
    claude, codex = _agent(_CLAUDE, "claude_code"), _agent(_CODEX, "codex")
    only_codex = _connection("a", active=True, scope=Scope(agents=[_CODEX]))
    out = _settled([claude, codex, only_codex])
    assert "connection_uid" not in out["claude-code"]
    assert out["codex"]["connection_uid"] == only_codex.uid


def test_where_two_active_connections_reach_an_agent_the_first_by_name_wins() -> None:
    claude = _agent(_CLAUDE, "claude_code")
    zed, alpha = _connection("z", active=True), _connection("a", active=True)
    assert _settled([claude, zed, alpha])["claude-code"]["connection_uid"] == alpha.uid


def test_an_inactive_disabled_or_keyless_connection_chooses_nothing() -> None:
    claude = _agent(_CLAUDE, "claude_code")
    for conn in (
        _connection("a", active=False),
        _connection("b", active=True, enabled=False),
        _connection("c", active=True, protocol="ollama"),
    ):
        out = _settled([claude, conn])
        assert "connection_uid" not in out["claude-code"], conn.name
        assert "is_active" not in out[conn.name]


def test_the_agents_wire_api_is_dropped() -> None:
    codex = _agent(_CODEX, "codex", wire_api="responses")
    assert "wire_api" not in _settled([codex])["codex"]


def test_every_converted_config_loads_under_the_current_models() -> None:
    claude, codex = _agent(_CLAUDE, "claude_code", wire_api="responses"), _agent(_CODEX, "codex")
    conn = _connection("a", active=True)
    for r in settle_connection_choice([claude, codex, conn]):
        if r.kind == "agent":
            assert AgentConfig.model_validate(r.config).connection_uid == conn.uid
        else:
            ProviderConfig.model_validate(r.config)


def test_an_agent_without_a_chosen_connection_loses_its_old_model_binding() -> None:
    binding = {"model": "agnes-2.0-flash", "effort": "low", "tier_models": {"haiku": "x"}}
    claude = _agent(_CLAUDE, "claude_code", **binding)
    codex = _agent(_CODEX, "codex", **binding)
    only_claude = _connection("a", active=True, scope=Scope(agents=[_CLAUDE]))
    out = _settled([claude, codex, only_claude])
    assert out["claude-code"]["model"] == "agnes-2.0-flash"
    for key in binding:
        assert key not in out["codex"]
    AgentConfig.model_validate(out["codex"])
