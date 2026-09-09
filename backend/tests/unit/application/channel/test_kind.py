"""make_channel_kind: Kind wiring + credential-ref extraction."""

from __future__ import annotations

import pytest

from coffer.application.channel.kind import make_channel_kind
from coffer.domain.channel.config import ChannelConfigModel
from coffer.domain.resource import ResourceRef


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


def _update_validate(config: dict, agent_keys=lambda: ["claude_code", "codex"]):
    hook = make_channel_kind(agent_keys=agent_keys).on_update_config
    assert hook is not None
    ref = ResourceRef(kind="channel", name="st")
    result = hook(ref, {"channel_type": "telegram"}, config)
    assert result is None  # synchronous validation, no awaitable


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


# -- scope shape validation (ADR-045 review Fix 1) ---------------------------
# A channel's platform identity tolerates only ONE machine consumer (ADR-043);
# `validate_scope_shape` rejects a scope map that would start its adapter on
# more than one machine, whether via two exact-ULID entries or the wildcard
# "*" key. Exercised directly against the Kind's callable — resource_scope_ops
# wraps a raised ValueError into ScopeInvalidError (covered end to end by the
# contract/CLI/integration tests).


def _shape_validator():
    validator = make_channel_kind().validate_scope_shape
    assert validator is not None
    return validator


def test_scope_shape_accepts_none():
    _shape_validator()(None)


def test_scope_shape_accepts_empty_dict():
    _shape_validator()({})


def test_scope_shape_accepts_single_machine_entry():
    _shape_validator()({"01ARZ3NDEKTSV4RRFFQ69G5FAV": "*"})


def test_scope_shape_rejects_two_machine_entries():
    with pytest.raises(ValueError, match="at most one machine"):
        _shape_validator()({"machine-1": "*", "machine-2": "*"})


def test_scope_shape_rejects_wildcard_key():
    with pytest.raises(ValueError, match="at most one machine"):
        _shape_validator()({"*": "*"})


def test_scope_shape_rejects_wildcard_key_even_alone():
    with pytest.raises(ValueError, match="at most one machine"):
        _shape_validator()({"*": "*", "machine-1": "*"})
