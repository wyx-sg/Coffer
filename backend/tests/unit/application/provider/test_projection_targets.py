"""Which agents a connection covers, and which it actually projects into.

``projection_targets`` is the seam four callers share — the switch, the
per-agent key lookup, the import reconcile and the boot self-heal — so the
answer cannot drift between them. ``scoped_targets`` is the CONFIGURED reach
the management surface reports, which is the same answer minus the ``enabled``
switch; the two are tested together here because the only thing that separates
them is that one input, and a change that collapsed them again would have to
break one of these tests.

The trap the pair was written for: framework ``scope is None`` means EVERY
agent, while the ``compatible_agents`` field it replaced meant "the wire
default" (nothing at all for ollama). Migration 0071 materialises every
existing row so no connection relies on that difference.
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
    resource, cfg = _connection(scope=Scope(agents=["claude_code"]))
    assert projection_targets(resource, cfg) == [AgentType.CLAUDE_CODE]


def test_an_unscoped_connection_reaches_every_agent() -> None:
    # The framework's own meaning for a null scope. Every pre-existing row was
    # materialised by 0071, so this is reachable only for a row scoped back to
    # null on purpose.
    resource, cfg = _connection(scope=None)
    assert projection_targets(resource, cfg) == list(AgentType)


def test_a_dormant_connection_reaches_nothing() -> None:
    resource, cfg = _connection(scope=Scope(agents=[]))
    assert projection_targets(resource, cfg) == []


def test_a_disabled_connection_reaches_nothing() -> None:
    # ``enabled`` is the user's switch on the resource; it beats everything.
    resource, cfg = _connection(scope=Scope(agents=["claude_code"]), enabled=False)
    assert projection_targets(resource, cfg) == []


def test_a_keyless_connection_reaches_nothing_whatever_its_scope_says() -> None:
    # ollama is Coffer's internal engine's endpoint: there is no key to write
    # into an agent's config, so a scope naming one is ignored rather than
    # producing a projection that cannot work.
    resource, cfg = _connection(protocol="ollama", scope=Scope(agents=["claude_code"]))
    assert projection_targets(resource, cfg) == []


def test_an_unknown_agent_name_in_the_scope_never_matches() -> None:
    resource, cfg = _connection(scope=Scope(agents=["codex", "retired-agent"]))
    assert projection_targets(resource, cfg) == [AgentType.CODEX]


# -- the configured reach, which `enabled` deliberately does NOT narrow --------


def test_the_configured_reach_survives_the_user_switching_the_connection_off() -> None:
    # The bug this pins: reporting the ENABLED-narrowed set on the wire made a
    # disabled connection's agent chips render as "—", so disabling looked like
    # it had erased the agent list and re-enabling looked like it restored data.
    # `enabled` travels on the same payload, so the client can intersect.
    resource, cfg = _connection(scope=Scope(agents=["claude_code"]), enabled=False)
    assert scoped_targets(resource, cfg) == [AgentType.CLAUDE_CODE]
    assert projection_targets(resource, cfg) == []


def test_the_two_agree_whenever_the_connection_is_enabled() -> None:
    for scope in (
        None,
        Scope(agents=[]),
        Scope(agents=["codex"]),
        Scope(agents=["claude_code", "codex"]),
    ):
        resource, cfg = _connection(scope=scope)
        assert scoped_targets(resource, cfg) == projection_targets(resource, cfg)


def test_a_keyless_connection_covers_nothing_even_as_configured_reach() -> None:
    # Unlike `enabled`, the ollama rule is not a switch the user flipped: there
    # is no key to write into any agent's config, so the connection does not
    # cover an agent even in principle and reporting one would be a lie.
    resource, cfg = _connection(protocol="ollama", scope=Scope(agents=["claude_code"]))
    assert scoped_targets(resource, cfg) == []
