"""make_channel_kind: Kind wiring + credential-ref extraction."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from coffer.application.channel.kind import make_channel_kind
from coffer.domain.channel.config import ChannelConfigModel
from coffer.domain.resource import Resource, ResourceRef

_NOW = datetime(2026, 9, 13, tzinfo=UTC)


def test_kind_named_channel_with_config_schema():
    kind = make_channel_kind()
    assert kind.name == "channel"
    assert kind.display_name == "Channel"
    assert kind.config_schema is ChannelConfigModel


def test_generic_create_allowed_defaults_true():
    assert make_channel_kind().generic_create_allowed is True


def test_on_delete_defaults_none_and_is_passed_through():
    assert make_channel_kind().on_delete is None

    async def evict(ref: ResourceRef) -> None:  # pragma: no cover - never awaited
        pass

    assert make_channel_kind(on_delete=evict).on_delete is evict


def test_extractor_pulls_telegram_bot_token_ref():
    extractor = make_channel_kind().credential_ref_extractor
    assert extractor is not None
    refs = extractor({"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-token"})
    assert refs == {"bot_token_ref": "channel/tg/bot-token"}


def test_extractor_pulls_both_seatalk_refs():
    extractor = make_channel_kind().credential_ref_extractor
    assert extractor is not None
    refs = extractor(
        {
            "channel_type": "seatalk",
            "app_id": "app-123",
            "app_secret_ref": "channel/st/app-secret",
            "signing_secret_ref": "channel/st/signing-secret",
        }
    )
    assert refs == {
        "app_secret_ref": "channel/st/app-secret",
        "signing_secret_ref": "channel/st/signing-secret",
    }


def test_extractor_skips_missing_empty_and_non_string_values():
    extractor = make_channel_kind().credential_ref_extractor
    assert extractor is not None
    refs = extractor(
        {
            "channel_type": "telegram",
            "bot_token_ref": "",  # empty: skipped
            "app_secret_ref": 123,  # non-string: skipped
            "signing_secret_ref": None,  # non-string: skipped
        }
    )
    assert refs == {}
    assert extractor({}) == {}


# -- default_agent validation -------------------------------------------------


def _validate(config: dict, agent_keys=lambda: ["claude_code", "codex"]):
    validator = make_channel_kind(agent_keys=agent_keys).validate_config
    assert validator is not None
    validator(config)


def test_validate_accepts_registered_default_agent():
    _validate({"channel_type": "telegram", "default_agent": "claude_code"})


def test_validate_rejects_unregistered_default_agent():
    with pytest.raises(ValueError, match="builtin"):
        _validate({"channel_type": "telegram", "default_agent": "builtin"})


def test_validate_skips_when_no_agent_keys_injected():
    # No agent_keys provider → backward-compatible, no agent validation.
    validator = make_channel_kind().validate_config
    assert validator is not None
    validator({"channel_type": "telegram", "default_agent": "builtin"})


def test_validate_skips_when_registry_empty():
    # An empty registry can't validate; never block all channel writes.
    _validate({"channel_type": "telegram", "default_agent": "builtin"}, agent_keys=list)


def test_validate_skips_when_default_agent_absent():
    _validate({"channel_type": "telegram"})


# -- default_agent validation on UPDATE ---------------------------------------
# validate_config runs at registration only (it also probes workspace dirs on
# disk). An edit that re-binds the channel to an unknown agent must still be
# rejected up front — otherwise the bot goes silently dead at turn time — so the
# channel Kind also wires an on_update_config hook that validates default_agent.


def _update_validate(config: dict, agent_keys=lambda: ["claude_code", "codex"], scope=None):
    async def _scope_of(_ref):
        return scope

    hook = make_channel_kind(agent_keys=agent_keys, scope_of=_scope_of).on_update_config
    assert hook is not None
    ref = ResourceRef(kind="channel", name="st")
    # Async because it reads the channel's scope off the row; ResourceService
    # awaits an awaitable hook result.
    asyncio.run(hook(ref, {"channel_type": "telegram"}, config))


def test_update_accepts_registered_default_agent():
    _update_validate({"channel_type": "telegram", "default_agent": "codex"})


def test_update_rejects_unregistered_default_agent():
    from coffer.domain.errors import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="builtin"):
        _update_validate({"channel_type": "telegram", "default_agent": "builtin"})


def test_update_skips_when_no_agent_keys_injected():
    # No agent_keys provider → no update hook wired (backward-compatible).
    assert make_channel_kind().on_update_config is None


def test_update_skips_when_registry_empty():
    _update_validate({"channel_type": "telegram", "default_agent": "builtin"}, agent_keys=list)


# -- per-agent scope (ADR per-agent-resource-scope) ----------------------------------------------
# Read the other way round from every other kind: a channel is an inbound
# surface no agent consumes, so its scope names the agents the channel may
# DRIVE. ``default_agent`` is held inside it at create and at edit; the
# `/agent` narrowing is covered in test_agent_routing.py.


def test_channel_kind_declares_scope():
    assert make_channel_kind().supports_scope is True


def test_channel_kind_has_no_starting_scope():
    # Unlike ``provider``, a new channel is unscoped — every agent — so
    # nothing changes for a channel created before scope reached this kind.
    assert make_channel_kind().default_scope is None


@pytest.mark.acceptance(
    spec="channels",
    scenario="a channel may only route to the agents in its scope",
)
def test_update_rejects_default_agent_outside_scope():
    from coffer.domain.errors import ConfigValidationError

    with pytest.raises(ConfigValidationError, match="outside this channel's scope"):
        _update_validate(
            {"channel_type": "telegram", "default_agent": "claude_code"}, scope=["codex"]
        )


def test_update_accepts_default_agent_inside_scope():
    _update_validate({"channel_type": "telegram", "default_agent": "codex"}, scope=["codex"])


def test_update_unscoped_channel_admits_every_registered_agent():
    # scope None is the pre-scope behaviour and must stay untouched.
    _update_validate({"channel_type": "telegram", "default_agent": "claude_code"}, scope=None)


@pytest.mark.acceptance(
    spec="channels",
    scenario="edit a dormant channel's configuration",
)
def test_update_on_a_dormant_channel_is_allowed():
    # ``scope == []`` means the channel is OFF, the same as for every other
    # kind — it must not also mean frozen, or a channel the owner deliberately
    # switched off could never have its bot token corrected.
    _update_validate({"channel_type": "telegram", "default_agent": "claude_code"}, scope=[])


def test_create_time_validation_needs_no_scope_reader():
    # A brand-new channel has no scope yet, so ``validate_config`` (sync, and
    # given only the config) is complete as it stands.
    _validate({"channel_type": "telegram", "default_agent": "claude_code"})


# -- the same invariant on the SCOPE write path (``validate_scope_for``) -------
# The config path holds an edited ``default_agent`` inside the scope; this holds
# an edited scope around the ``default_agent``. Both exist so the inconsistent
# state — a channel scoped away from the agent it drives — cannot be stored at
# all, whichever path the write arrives on.


def _validate_scope(scope, config=None):
    hook = make_channel_kind().validate_scope_for
    assert hook is not None
    resource = Resource(
        id=1,
        kind="channel",
        name="tg",
        description=None,
        config=config if config is not None else {"channel_type": "telegram"},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )
    hook(resource, scope)


def test_scope_hook_is_always_wired():
    # It judges a proposed scope against the channel's own stored config, so
    # unlike ``on_update_config`` it needs nothing injected and is never absent.
    assert make_channel_kind().validate_scope_for is not None


@pytest.mark.acceptance(
    spec="channels",
    scenario="reject narrowing a channel's scope past its default agent",
)
def test_scope_narrowed_past_the_default_agent_is_rejected():
    with pytest.raises(ValueError, match="claude_code"):
        _validate_scope(["codex"])


def test_scope_rejection_names_the_proposed_scope_too():
    # Both sides, so the owner can see the two ways out of it.
    with pytest.raises(ValueError, match="codex"):
        _validate_scope(["codex"], {"channel_type": "telegram", "default_agent": "claude_code"})


def test_scope_containing_the_default_agent_is_accepted():
    _validate_scope(["claude_code", "codex"])


def test_a_channel_with_an_explicit_default_agent_is_read_from_its_config():
    _validate_scope(["codex"], {"channel_type": "telegram", "default_agent": "codex"})


@pytest.mark.acceptance(
    spec="channels",
    scenario="a channel scoped to no agent is dormant",
)
def test_the_dormant_scope_is_always_accepted():
    _validate_scope([])


def test_clearing_the_scope_is_always_accepted():
    _validate_scope(None)
