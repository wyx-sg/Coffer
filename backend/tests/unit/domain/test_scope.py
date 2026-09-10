"""Per-agent activation scope semantics (ADR per-agent-resource-scope, single-axis).

The machine axis was withdrawn with continuous sync (ADR vault-export-import); scope is now
a plain agent-name list.
"""

import pytest

from coffer.domain.scope import (
    ScopeValidationError,
    agent_in_scope,
    validate_scope,
)


def test_none_scope_matches_every_agent():
    assert agent_in_scope(None, "claude-code") is True
    assert agent_in_scope(None, None) is True


def test_empty_scope_matches_nothing():
    assert agent_in_scope([], "claude-code") is False
    assert agent_in_scope([], None) is False


def test_listed_agent_matches():
    assert agent_in_scope(["claude-code"], "claude-code") is True
    assert agent_in_scope(["claude-code"], "codex") is False
    assert agent_in_scope(["claude-code", "codex"], "codex") is True


def test_unidentified_session_only_matches_unscoped():
    assert agent_in_scope(["claude-code"], None) is False


def test_unknown_agent_names_are_legal_and_never_match():
    # Scoping in an agent before it is registered is allowed.
    validate_scope(["not-installed-yet"], supports_scope=True)
    assert agent_in_scope(["not-installed-yet"], "claude-code") is False


def test_kind_without_scope_rejects_non_null():
    with pytest.raises(ScopeValidationError):
        validate_scope(["claude-code"], supports_scope=False)
    with pytest.raises(ScopeValidationError):
        validate_scope([], supports_scope=False)
    # Clearing scope is always allowed, even for a kind that has none.
    validate_scope(None, supports_scope=False)


def test_scope_supporting_kind_accepts_null_empty_and_lists():
    validate_scope(None, supports_scope=True)
    validate_scope([], supports_scope=True)
    validate_scope(["claude-code", "codex"], supports_scope=True)


def test_validate_rejects_malformed():
    for bad in ("claude-code", 1, {"m": "*"}, ["ok", 1], [""], [None]):
        with pytest.raises(ScopeValidationError):
            validate_scope(bad, supports_scope=True)
