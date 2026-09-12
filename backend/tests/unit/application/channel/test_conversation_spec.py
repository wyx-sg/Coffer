"""The conversation-spec resolver: how a peer's sticky choices + channel
defaults become (agent_key, agent_config)."""

from __future__ import annotations

from coffer.application.channel.conversation_spec import (
    ConversationSpec,
    narrow_to_allowed,
    refuse_model,
    resolve_conversation_spec,
)


def _resolve(**overrides):  # type: ignore[no-untyped-def]
    kwargs = {
        "default_agent": "builtin",
        "default_agent_config": None,
        "preferred_agent": None,
        "default_model": None,
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


# --- the channel's own model curation (FR-071) --------------------------------


def test_no_default_model_pins_nothing():
    """An unconfigured channel writes no ``model`` at all, so the agent's CLI
    default applies — exactly what it did before the field existed."""
    spec = _resolve()
    assert spec.agent_config is None


def test_the_default_model_reaches_a_new_conversations_agent_config():
    spec = _resolve(default_model="claude-opus-5")
    assert spec.agent_config == {"model": "claude-opus-5"}


def test_the_default_model_joins_the_rest_of_the_agent_config():
    spec = _resolve(default_agent_config={"cwd": "/tmp"}, default_model="claude-opus-5")
    assert spec.agent_config == {"cwd": "/tmp", "model": "claude-opus-5"}


def test_the_default_model_field_outranks_a_model_left_in_the_raw_blob():
    """The blob is provider passthrough; the field is the setting the user
    edited, and it is the one the channel editor writes."""
    spec = _resolve(default_agent_config={"model": "stale"}, default_model="claude-opus-5")
    assert spec.agent_config == {"model": "claude-opus-5"}


def test_an_empty_default_model_leaves_the_blob_alone():
    spec = _resolve(default_agent_config={"model": "from-blob"}, default_model=None)
    assert spec.agent_config == {"model": "from-blob"}


def test_an_uncurated_channel_offers_everything_the_agent_offers():
    assert narrow_to_allowed(["a", "b", "c"], []) == ["a", "b", "c"]


def test_a_curated_channel_offers_its_own_range_in_its_own_order():
    """The user arranged that list; the agent's discovery order does not
    outrank it."""
    assert narrow_to_allowed(["a", "b", "c"], ["c", "a"]) == ["c", "a"]


def test_an_allowed_id_the_agent_no_longer_reports_is_still_offered():
    """The channel is the authority on what this chat may run, and an id Coffer
    does not recognise is passed to the CLI verbatim anyway."""
    assert narrow_to_allowed(["a"], ["a", "some-model-from-next-year"]) == [
        "a",
        "some-model-from-next-year",
    ]


def test_an_uncurated_channel_refuses_no_model():
    assert refuse_model("anything-at-all", []) is None


def test_a_model_inside_the_range_is_allowed():
    assert refuse_model("b", ["a", "b"]) is None


def test_a_model_outside_the_range_is_refused_naming_what_is_allowed():
    message = refuse_model("c", ["a", "b"])
    assert message is not None
    assert "c" in message
    assert "a, b" in message
