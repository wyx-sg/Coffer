"""The conversation-spec resolver: how a peer's sticky choices + channel
defaults become (agent_key, agent_config)."""

from __future__ import annotations

from coffer.application.channel.conversation_spec import (
    ConversationSpec,
    resolve_conversation_spec,
)


def _resolve(**overrides):  # type: ignore[no-untyped-def]
    kwargs = {
        "default_agent": "builtin",
        "default_agent_config": None,
        "preferred_agent": None,
    }
    kwargs.update(overrides)
    return resolve_conversation_spec(**kwargs)


def test_builtin_default_resolves_with_no_config():
    spec = _resolve()
    assert spec == ConversationSpec(agent_key="builtin", agent_config=None)


def test_preferred_agent_overrides_default():
    spec = _resolve(preferred_agent="codex")
    assert spec.agent_key == "codex"


def test_no_workspace_resolved_keeps_default_config():
    spec = _resolve(preferred_agent="codex", default_agent_config={"k": "v"})
    assert spec.agent_config == {"k": "v"}
