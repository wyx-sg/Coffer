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


def test_a_channel_pins_no_model_so_the_agents_cli_default_applies():
    """A channel curates no models: the resolver writes no ``model`` key at all
    and a fresh conversation opens on whatever the agent's CLI defaults to."""
    spec = _resolve()
    assert spec.agent_config is None


def test_a_model_left_in_the_raw_config_blob_is_passed_through_untouched():
    """The blob is provider passthrough; nothing on the channel overrides it."""
    spec = _resolve(default_agent_config={"model": "from-blob"})
    assert spec.agent_config == {"model": "from-blob"}
