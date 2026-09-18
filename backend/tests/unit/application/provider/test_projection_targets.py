"""Which agents a connection covers, and which it actually projects into.

``projection_targets`` is the seam four callers share — the switch, the
per-agent key lookup, the import reconcile and the boot self-heal — so the
answer cannot drift between them. ``scoped_targets`` is the CONFIGURED reach
the management surface reports, which is the same answer minus the ``enabled``
switch; the two are tested together here because the only thing that separates
them is that one input, and a change that collapsed them again would have to
break one of these tests.

Two traps the pair was written for:

- framework ``scope is None`` means EVERY agent, while the
  ``compatible_agents`` field it replaced meant "the wire default" (nothing at
  all for ollama); and
- a scope holds agent UIDS (ADR resource-identity-is-an-immutable-uid), so the
  reach is not readable from the connection alone. It used to be: the list held
  agent TYPE values and a string comparison answered the question. That was one
  of the three private vocabularies the uid removed, and the tests below are
  what stop it coming back — every one of them has to hand the registry in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coffer.application.provider.targets import projection_targets, scoped_targets
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope

_NOW = datetime(2026, 9, 13, tzinfo=UTC)

_CLAUDE_UID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_CODEX_UID = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _agent(uid: str, agent_type: AgentType, *, enabled: bool = True) -> Resource:
    return Resource(
        id=1,
        uid=uid,
        kind="agent",
        name=agent_type.default_name(),
        description=None,
        config={"type": agent_type.value, "config_dir": f"/tmp/{agent_type.value}"},
        enabled=enabled,
        created_at=_NOW,
        updated_at=_NOW,
    )


#: The registry every case resolves its scope against: one agent of each type.
_REGISTRY = [_agent(_CLAUDE_UID, AgentType.CLAUDE_CODE), _agent(_CODEX_UID, AgentType.CODEX)]


def _connection(
    *,
    protocol: str = "openai",
    scope: Scope | None = None,
    enabled: bool = True,
) -> tuple[Resource, ProviderConfig]:
    config: dict[str, Any] = {"protocol": protocol, "base_url": "https://gw/v1"}
    if protocol != "ollama":
        config["credential_ref"] = "provider/x/key"
    resource = Resource(
        id=1,
        uid="cccccccccccccccccccccccccccccccc",
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
    assert projection_targets(resource, cfg, _REGISTRY) == [AgentType.CLAUDE_CODE]


def test_the_reach_is_the_uid_resolved_against_the_registry_not_a_string_match() -> None:
    # The whole point of the seam: nothing about the uid says "claude_code", so
    # the same scope answers differently depending on which agent that uid is.
    # A comparison against ``AgentType`` values — what this module did while
    # scopes held type names — would answer nothing at all for either.
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]))
    swapped = [_agent(_CLAUDE_UID, AgentType.CODEX)]
    assert projection_targets(resource, cfg, swapped) == [AgentType.CODEX]


def test_an_unscoped_connection_reaches_every_agent() -> None:
    # The framework's own meaning for a null scope, and what a credentialed
    # connection is now CREATED with — including agent types not registered on
    # this machine, so a connection made before the user installed Codex still
    # covers it.
    resource, cfg = _connection(scope=None)
    assert projection_targets(resource, cfg, []) == list(AgentType)


def test_a_dormant_connection_reaches_nothing() -> None:
    resource, cfg = _connection(scope=Scope(agents=[]))
    assert projection_targets(resource, cfg, _REGISTRY) == []


def test_a_disabled_connection_reaches_nothing() -> None:
    # ``enabled`` is the user's switch on the resource; it beats everything.
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]), enabled=False)
    assert projection_targets(resource, cfg, _REGISTRY) == []


def test_a_keyless_connection_reaches_nothing_whatever_its_scope_says() -> None:
    # ollama is Coffer's internal engine's endpoint: there is no key to write
    # into an agent's config, so a scope naming one is ignored rather than
    # producing a projection that cannot work.
    resource, cfg = _connection(protocol="ollama", scope=Scope(agents=[_CLAUDE_UID]))
    assert projection_targets(resource, cfg, _REGISTRY) == []


def test_a_uid_no_registered_agent_answers_to_never_matches() -> None:
    # A resource may be scoped to an agent this machine does not have (the
    # scope layer's own rule). It contributes no type — dropped, never guessed
    # at, so the reach narrows and never widens.
    resource, cfg = _connection(scope=Scope(agents=[_CODEX_UID, "deadbeef" * 4]))
    assert projection_targets(resource, cfg, _REGISTRY) == [AgentType.CODEX]


def test_an_agent_the_user_switched_off_still_contributes_its_type() -> None:
    # ``enabled`` on the AGENT is the projector's business at write time. If it
    # narrowed the reach here, ``activate``'s ``skipped`` list would go silent
    # about the very case it exists to report.
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]))
    registry = [_agent(_CLAUDE_UID, AgentType.CLAUDE_CODE, enabled=False)]
    assert projection_targets(resource, cfg, registry) == [AgentType.CLAUDE_CODE]


def test_an_agent_row_that_no_longer_parses_contributes_nothing() -> None:
    broken = _agent(_CLAUDE_UID, AgentType.CLAUDE_CODE)
    broken.config = {"type": "a product Coffer has never heard of"}
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]))
    assert projection_targets(resource, cfg, [broken]) == []


# -- the configured reach, which `enabled` deliberately does NOT narrow --------


def test_the_configured_reach_survives_the_user_switching_the_connection_off() -> None:
    # The bug this pins: reporting the ENABLED-narrowed set on the wire made a
    # disabled connection's agent chips render as "—", so disabling looked like
    # it had erased the agent list and re-enabling looked like it restored data.
    # `enabled` travels on the same payload, so the client can intersect.
    resource, cfg = _connection(scope=Scope(agents=[_CLAUDE_UID]), enabled=False)
    assert scoped_targets(resource, cfg, _REGISTRY) == [AgentType.CLAUDE_CODE]
    assert projection_targets(resource, cfg, _REGISTRY) == []


def test_the_two_agree_whenever_the_connection_is_enabled() -> None:
    for scope in (
        None,
        Scope(agents=[]),
        Scope(agents=[_CODEX_UID]),
        Scope(agents=[_CLAUDE_UID, _CODEX_UID]),
    ):
        resource, cfg = _connection(scope=scope)
        assert scoped_targets(resource, cfg, _REGISTRY) == projection_targets(
            resource, cfg, _REGISTRY
        )


def test_a_keyless_connection_covers_nothing_even_as_configured_reach() -> None:
    # Unlike `enabled`, the ollama rule is not a switch the user flipped: there
    # is no key to write into any agent's config, so the connection does not
    # cover an agent even in principle and reporting one would be a lie.
    resource, cfg = _connection(protocol="ollama", scope=Scope(agents=[_CLAUDE_UID]))
    assert scoped_targets(resource, cfg, _REGISTRY) == []
