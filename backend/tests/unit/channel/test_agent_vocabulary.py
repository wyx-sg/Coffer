"""The two names an agent has, and the one vocabulary the comparison happens in.

A channel's `default_agent` is a turn-platform agent key (`claude_code`); a
scope is a list of registry names (`claude-code`). Comparing them directly
rejected every correctly-narrowed scope, and admitted only the value the reach
picker then had to render as "not registered here".
"""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.application.channel.agent_vocabulary import (
    agent_key_by_name,
    as_agent_keys,
    drives,
    scope_agent_keys,
)
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope

TYPES = {"claude-code": "claude_code", "codex": "codex"}


def test_a_scope_naming_the_registry_name_drives_that_agents_key() -> None:
    # The case that was broken: the only name the picker offers, refused.
    assert drives(Scope(agents=["claude-code"]), "claude_code", TYPES) is True


def test_a_scope_that_excludes_the_agent_still_excludes_it() -> None:
    # The invariant is real and must survive the translation.
    assert drives(Scope(agents=["codex"]), "claude_code", TYPES) is False


def test_an_unrestricted_scope_drives_anything() -> None:
    assert drives(None, "claude_code", TYPES) is True
    assert drives(Scope(agents=None), "claude_code", TYPES) is True


def test_an_empty_scope_drives_nothing() -> None:
    # Dormant: the channel is off. Not an error, and not "everything".
    assert drives(Scope(agents=[]), "claude_code", TYPES) is False


def test_a_name_the_registry_does_not_know_admits_nobody() -> None:
    # It maps to no agent key, so it cannot admit one — and passing it through
    # would let it masquerade as an agent key in the error message.
    assert drives(Scope(agents=["desktop-only"]), "claude_code", TYPES) is False
    assert scope_agent_keys(Scope(agents=["desktop-only"]), TYPES) == []


def test_two_registry_names_of_the_same_type_collapse_to_one_key() -> None:
    # Two Claude Code agents registered against different config dirs are two
    # resources and one agent key; a scope naming either drives that key.
    types = {"cc-work": "claude_code", "cc-home": "claude_code"}
    assert scope_agent_keys(Scope(agents=["cc-work", "cc-home"]), types) == ["claude_code"]
    assert drives(Scope(agents=["cc-home"]), "claude_code", types) is True


def test_every_agent_is_reported_as_no_restriction_not_as_a_list() -> None:
    assert scope_agent_keys(None, TYPES) is None


def _agent(name: str, config: dict[str, object]) -> Resource:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    return Resource(
        id=1,
        kind="agent",
        name=name,
        config=config,
        description=None,
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def test_the_map_is_built_from_the_registered_agent_resources() -> None:
    rows = [_agent("claude-code", {"type": "claude_code"}), _agent("codex", {"type": "codex"})]
    assert agent_key_by_name(rows) == TYPES


def test_a_row_carrying_no_agent_type_names_no_agent() -> None:
    # Nothing to translate to, so the name admits nobody rather than admitting
    # itself — a scope naming it is a scope that drives nothing.
    rows = [_agent("broken", {}), _agent("codex", {"type": "codex"})]
    assert agent_key_by_name(rows) == {"codex": "codex"}
    assert drives(Scope(agents=["broken"]), "codex", agent_key_by_name(rows)) is False


def test_a_scope_is_rewritten_into_the_vocabulary_the_binding_speaks() -> None:
    # What the runtime stamps onto the binding, so `/agent` and the router below
    # it never see a registry name at all.
    assert as_agent_keys(Scope(agents=["claude-code"]), TYPES) == Scope(agents=["claude_code"])
    assert as_agent_keys(None, TYPES) is None
    assert as_agent_keys(Scope(agents=[]), TYPES) == Scope(agents=[])
