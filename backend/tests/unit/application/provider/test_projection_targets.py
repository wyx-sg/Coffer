"""Which agents a connection reaches, and which connection an agent runs on.

``scoped_targets`` is the CONFIGURED reach the management surface reports: what
the connection's addresses serve (ADR provider-reach-is-what-its-addresses-serve).
``reaches`` is one agent's effective reach (the ``enabled`` switch applied) and
``connection_for_agent`` is the ONE function every consumer — the switch, the
model proxy's state, the projection reconcile target, the chat model catalogue
and the usage meter — asks which connection an agent runs on, so the answer
cannot drift between them. A scope stored before the rule is ignored.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coffer.application.provider.targets import connection_for_agent, reaches, scoped_targets
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope

_NOW = datetime(2026, 9, 13, tzinfo=UTC)

_CLAUDE_UID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_CODEX_UID = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _agent(
    uid: str,
    agent_type: AgentType,
    *,
    enabled: bool = True,
    connection_uid: str | None = None,
) -> Resource:
    return Resource(
        uid=uid,
        kind="agent",
        name=agent_type.default_name(),
        description=None,
        config={
            "type": agent_type.value,
            "config_dir": f"/tmp/{agent_type.value}",
            "connection_uid": connection_uid,
        },
        enabled=enabled,
        created_at=_NOW,
        updated_at=_NOW,
    )


#: The registry: one agent of each type.
_REGISTRY = [_agent(_CLAUDE_UID, AgentType.CLAUDE_CODE), _agent(_CODEX_UID, AgentType.CODEX)]

_CONN_UID = "cccccccccccccccccccccccccccccccc"


def _connection(
    *,
    protocol: str = "openai",
    scope: Scope | None = None,
    enabled: bool = True,
    anthropic_base_url: str | None = "https://gw",
) -> tuple[Resource, ProviderConfig]:
    # A gateway serving both wires by default.
    config: dict[str, Any] = {"protocol": protocol, "base_url": "https://gw/v1"}
    if protocol != "ollama":
        config["secret_ref"] = "provider/x/key"
    if protocol == "openai" and anthropic_base_url:
        config["anthropic_base_url"] = anthropic_base_url
    resource = Resource(
        uid=_CONN_UID,
        kind="provider",
        name="gw",
        description=None,
        config=config,
        enabled=enabled,
        created_at=_NOW,
        updated_at=_NOW,
        scope=scope,
    )
    return resource, ProviderConfig.model_validate(config)


def test_a_keyless_connection_covers_nothing_even_as_configured_reach() -> None:
    # Unlike `enabled`, the ollama rule is not a switch the user flipped: there
    # is no key to write into any agent's config, so the connection does not
    # cover an agent even in principle and reporting one would be a lie.
    resource, cfg = _connection(protocol="ollama", scope=Scope(agents=[_CLAUDE_UID]))
    assert scoped_targets(resource, cfg, _REGISTRY) == []
    assert not reaches(resource, cfg, _REGISTRY[0])


# -- the connection an agent runs on -------------------------------------------


def test_an_agent_runs_on_the_connection_its_record_names() -> None:
    resource, cfg = _connection(scope=None)
    agent = _agent(_CLAUDE_UID, AgentType.CLAUDE_CODE, connection_uid=_CONN_UID)
    found = connection_for_agent(agent, [resource])
    assert found is not None
    assert found[0].uid == _CONN_UID
    assert found[1] == cfg


def test_an_agent_with_no_choice_runs_on_no_connection() -> None:
    resource, _ = _connection(scope=None)
    assert connection_for_agent(_agent(_CLAUDE_UID, AgentType.CLAUDE_CODE), [resource]) is None


def test_the_choice_is_per_agent_so_a_sibling_on_the_same_connection_is_untouched() -> None:
    resource, _ = _connection(scope=None)
    on = _agent(_CLAUDE_UID, AgentType.CLAUDE_CODE, connection_uid=_CONN_UID)
    off = _agent(_CODEX_UID, AgentType.CODEX)
    assert connection_for_agent(on, [resource]) is not None
    assert connection_for_agent(off, [resource]) is None


def test_a_pointer_that_names_a_missing_connection_is_no_connection() -> None:
    resource, _ = _connection(scope=None)
    agent = _agent(_CLAUDE_UID, AgentType.CLAUDE_CODE, connection_uid="f" * 32)
    assert connection_for_agent(agent, [resource]) is None


def test_a_pointer_is_not_followed_to_a_disabled_connection() -> None:
    resource, _ = _connection(scope=None, enabled=False)
    agent = _agent(_CLAUDE_UID, AgentType.CLAUDE_CODE, connection_uid=_CONN_UID)
    assert connection_for_agent(agent, [resource]) is None


def test_a_pointer_is_not_followed_to_a_keyless_connection() -> None:
    resource, _ = _connection(protocol="ollama", scope=None)
    agent = _agent(_CLAUDE_UID, AgentType.CLAUDE_CODE, connection_uid=_CONN_UID)
    assert connection_for_agent(agent, [resource]) is None


def test_an_anthropic_connection_covers_only_claude_code() -> None:
    resource, cfg = _connection(protocol="anthropic", scope=None)
    assert scoped_targets(resource, cfg, _REGISTRY) == [AgentType.CLAUDE_CODE]


def test_the_reach_is_what_the_addresses_serve_whatever_a_stored_scope_says() -> None:
    # ADR provider-reach-is-what-its-addresses-serve: a scope stored before
    # the rule neither narrows nor widens it.
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]))
    assert scoped_targets(resource, cfg, _REGISTRY) == [AgentType.CLAUDE_CODE, AgentType.CODEX]
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]), anthropic_base_url=None)
    assert scoped_targets(resource, cfg, _REGISTRY) == [AgentType.CODEX]
    assert not reaches(resource, cfg, _REGISTRY[0])
    assert reaches(resource, cfg, _REGISTRY[1])


def test_the_configured_reach_survives_the_connection_being_off() -> None:
    resource, cfg = _connection(enabled=False)
    assert scoped_targets(resource, cfg, _REGISTRY) == [AgentType.CLAUDE_CODE, AgentType.CODEX]
    assert not reaches(resource, cfg, _REGISTRY[0])


def test_a_pointer_is_not_followed_to_a_connection_with_no_address_for_the_agent() -> None:
    resource, _ = _connection(anthropic_base_url=None)
    agent = _agent(_CLAUDE_UID, AgentType.CLAUDE_CODE, connection_uid=_CONN_UID)
    assert connection_for_agent(agent, [resource]) is None
