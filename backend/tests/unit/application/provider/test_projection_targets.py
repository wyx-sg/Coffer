"""Which agents a connection reaches, and which connection an agent runs on.

``scoped_targets`` is the CONFIGURED reach the management surface reports.
``reaches`` is one agent's effective reach (the ``enabled`` switch applied) and
``connection_for_agent`` is the ONE function every consumer — the switch, the
model proxy's state, the projection reconcile target, the chat model catalogue
and the usage meter — asks which connection an agent runs on, so the answer
cannot drift between them.

Two traps the reach was written for:

- framework ``scope is None`` means EVERY agent, while the
  ``compatible_agents`` field it replaced meant "the wire default" (nothing at
  all for ollama); and
- a scope holds agent UIDS (ADR identity-is-the-uid-inside-the-file), so the
  reach per TYPE is not readable from the connection alone: the registry has to
  be handed in.
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


#: The registry every case resolves its scope against: one agent of each type.
_REGISTRY = [_agent(_CLAUDE_UID, AgentType.CLAUDE_CODE), _agent(_CODEX_UID, AgentType.CODEX)]

_CONN_UID = "cccccccccccccccccccccccccccccccc"


def _connection(
    *,
    protocol: str = "openai",
    scope: Scope | None = None,
    enabled: bool = True,
) -> tuple[Resource, ProviderConfig]:
    config: dict[str, Any] = {"protocol": protocol, "base_url": "https://gw/v1"}
    if protocol != "ollama":
        config["secret_ref"] = "provider/x/key"
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


def test_an_explicit_scope_is_the_reach() -> None:
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]))
    assert scoped_targets(resource, cfg, _REGISTRY) == [AgentType.CLAUDE_CODE]


def test_the_reach_is_the_uid_resolved_against_the_registry_not_a_string_match() -> None:
    # Nothing about the uid says "claude_code", so the same scope answers
    # differently depending on which agent that uid is.
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]))
    swapped = [_agent(_CLAUDE_UID, AgentType.CODEX)]
    assert scoped_targets(resource, cfg, swapped) == [AgentType.CODEX]


def test_an_unscoped_connection_reaches_every_agent() -> None:
    # The framework's own meaning for a null scope, and what a credentialed
    # connection is CREATED with — including agent types not registered on this
    # machine, so a connection made before the user installed Codex still
    # covers it.
    resource, cfg = _connection(scope=None)
    assert scoped_targets(resource, cfg, []) == list(AgentType)


def test_a_dormant_connection_reaches_nothing() -> None:
    resource, cfg = _connection(scope=Scope(agents=[]))
    assert scoped_targets(resource, cfg, _REGISTRY) == []


def test_a_uid_no_registered_agent_answers_to_never_matches() -> None:
    # A resource may be scoped to an agent this machine does not have (the
    # scope layer's own rule). It contributes no type — dropped, never guessed
    # at, so the reach narrows and never widens.
    resource, cfg = _connection(scope=Scope(agents=[_CODEX_UID, "deadbeef" * 4]))
    assert scoped_targets(resource, cfg, _REGISTRY) == [AgentType.CODEX]


def test_an_agent_row_that_no_longer_parses_contributes_nothing() -> None:
    broken = _agent(_CLAUDE_UID, AgentType.CLAUDE_CODE)
    broken.config = {"type": "a product Coffer has never heard of"}
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]))
    assert scoped_targets(resource, cfg, [broken]) == []


def test_the_configured_reach_survives_the_user_switching_the_connection_off() -> None:
    # Reporting the ENABLED-narrowed set on the wire made a disabled
    # connection's agent chips render as "—", so disabling looked like it had
    # erased the agent list. `enabled` travels on the same payload, so the
    # client can intersect.
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]), enabled=False)
    assert scoped_targets(resource, cfg, _REGISTRY) == [AgentType.CLAUDE_CODE]
    assert not reaches(resource, cfg, _REGISTRY[0])


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


def test_a_pointer_is_not_followed_to_a_connection_whose_scope_dropped_the_agent() -> None:
    resource, _ = _connection(scope=Scope(agents=[_CODEX_UID]))
    agent = _agent(_CLAUDE_UID, AgentType.CLAUDE_CODE, connection_uid=_CONN_UID)
    assert connection_for_agent(agent, [resource]) is None


def test_a_pointer_is_not_followed_to_a_keyless_connection() -> None:
    resource, _ = _connection(protocol="ollama", scope=None)
    agent = _agent(_CLAUDE_UID, AgentType.CLAUDE_CODE, connection_uid=_CONN_UID)
    assert connection_for_agent(agent, [resource]) is None
