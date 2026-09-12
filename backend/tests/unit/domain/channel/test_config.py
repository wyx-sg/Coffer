"""Channel config value objects: discriminated union + raw-secret rejection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.channel.config import (
    ChannelConfigModel,
    SeaTalkChannelConfig,
    TelegramChannelConfig,
    parse_channel_config,
)

TELEGRAM_CONFIG = {
    "channel_type": "telegram",
    "bot_token_ref": "channel/tg/bot-token",
}

SEATALK_CONFIG = {
    "channel_type": "seatalk",
    "app_id": "app-123",
    "app_secret_ref": "channel/st/app-secret",
    "signing_secret_ref": "channel/st/signing-secret",
}


def test_public_base_url_defaults_none_and_accepts_https():
    assert parse_channel_config(SEATALK_CONFIG).public_base_url is None
    cfg = parse_channel_config({**SEATALK_CONFIG, "public_base_url": "https://x.trycloudflare.com"})
    assert cfg.public_base_url == "https://x.trycloudflare.com"


def test_public_base_url_strips_trailing_slash_and_blank_to_none():
    cfg = parse_channel_config({**SEATALK_CONFIG, "public_base_url": "https://x.example.com/"})
    assert cfg.public_base_url == "https://x.example.com"
    assert parse_channel_config({**SEATALK_CONFIG, "public_base_url": "  "}).public_base_url is None


def test_public_base_url_rejects_non_https():
    with pytest.raises(ValidationError, match="https"):
        parse_channel_config({**SEATALK_CONFIG, "public_base_url": "http://x.example.com"})


def test_public_base_url_rejects_path():
    with pytest.raises(ValidationError, match="no path"):
        parse_channel_config({**SEATALK_CONFIG, "public_base_url": "https://x.example.com/seatalk"})


def test_tunnel_token_ref_defaults_none_and_accepts_a_ref():
    assert parse_channel_config(SEATALK_CONFIG).tunnel_token_ref is None
    cfg = parse_channel_config({**SEATALK_CONFIG, "tunnel_token_ref": "channel/st/tunnel-token"})
    assert cfg.tunnel_token_ref == "channel/st/tunnel-token"


def test_tunnel_token_ref_rejects_raw_secret():
    with pytest.raises(ValidationError, match="raw secret"):
        parse_channel_config({**SEATALK_CONFIG, "tunnel_token_ref": "A" * 60})


WEBSOCKET_CONFIG = {
    "channel_type": "seatalk",
    "app_id": "app-123",
    "app_secret_ref": "channel/st/app-secret",
    "delivery": "websocket",
}


def test_delivery_defaults_to_webhook():
    """A stored config written before the field existed IS a webhook channel;
    the default says so rather than forcing a migration to restate it."""
    assert parse_channel_config(SEATALK_CONFIG).delivery == "webhook"


def test_webhook_delivery_requires_a_signing_secret_ref():
    with pytest.raises(ValidationError, match="signing_secret_ref is required"):
        parse_channel_config({k: v for k, v in SEATALK_CONFIG.items() if k != "signing_secret_ref"})


def test_webhook_delivery_accepts_public_url_and_tunnel_token():
    cfg = parse_channel_config(
        {
            **SEATALK_CONFIG,
            "delivery": "webhook",
            "public_base_url": "https://x.example.com",
            "tunnel_token_ref": "channel/st/tunnel-token",
        }
    )
    assert cfg.delivery == "webhook"
    assert cfg.public_base_url == "https://x.example.com"
    assert cfg.tunnel_token_ref == "channel/st/tunnel-token"


def test_websocket_delivery_needs_only_the_app_credentials():
    cfg = parse_channel_config(WEBSOCKET_CONFIG)
    assert cfg.delivery == "websocket"
    assert cfg.app_id == "app-123"
    assert cfg.app_secret_ref == "channel/st/app-secret"
    # Nothing webhook-shaped is left behind to imply ingress that does not exist.
    assert cfg.signing_secret_ref is None
    assert cfg.public_base_url is None
    assert cfg.tunnel_token_ref is None


def test_websocket_delivery_still_requires_app_id_and_secret_ref():
    """The register handshake authenticates with exactly these two."""
    with pytest.raises(ValidationError):
        parse_channel_config({k: v for k, v in WEBSOCKET_CONFIG.items() if k != "app_id"})
    with pytest.raises(ValidationError):
        parse_channel_config({k: v for k, v in WEBSOCKET_CONFIG.items() if k != "app_secret_ref"})


@pytest.mark.parametrize(
    "field,value",
    [
        ("signing_secret_ref", "channel/st/signing-secret"),
        ("public_base_url", "https://x.example.com"),
        ("tunnel_token_ref", "channel/st/tunnel-token"),
    ],
)
def test_websocket_delivery_forbids_every_webhook_only_field(field: str, value: str):
    with pytest.raises(ValidationError, match=f"{field} must be empty"):
        parse_channel_config({**WEBSOCKET_CONFIG, field: value})


def test_websocket_rejection_names_every_offending_field_at_once():
    with pytest.raises(ValidationError) as excinfo:
        parse_channel_config(
            {
                **WEBSOCKET_CONFIG,
                "signing_secret_ref": "channel/st/signing-secret",
                "public_base_url": "https://x.example.com",
                "tunnel_token_ref": "channel/st/tunnel-token",
            }
        )
    message = str(excinfo.value)
    assert "signing_secret_ref, public_base_url, tunnel_token_ref must be empty" in message


def test_unknown_delivery_method_rejected():
    with pytest.raises(ValidationError):
        parse_channel_config({**WEBSOCKET_CONFIG, "delivery": "grpc"})


def test_parse_valid_telegram_config():
    cfg = parse_channel_config(TELEGRAM_CONFIG)
    assert isinstance(cfg, TelegramChannelConfig)
    assert cfg.channel_type == "telegram"
    assert cfg.bot_token_ref == "channel/tg/bot-token"


def test_parse_valid_seatalk_config():
    cfg = parse_channel_config(SEATALK_CONFIG)
    assert isinstance(cfg, SeaTalkChannelConfig)
    assert cfg.channel_type == "seatalk"
    assert cfg.app_id == "app-123"
    assert cfg.app_secret_ref == "channel/st/app-secret"
    assert cfg.signing_secret_ref == "channel/st/signing-secret"


def test_channel_type_discriminates_union():
    """The same extra fields land on the model picked by channel_type."""
    cfg = parse_channel_config({**SEATALK_CONFIG})
    assert isinstance(cfg, SeaTalkChannelConfig)
    with pytest.raises(ValidationError):
        parse_channel_config({"channel_type": "slack", "bot_token_ref": "a/b"})


def test_missing_channel_type_rejected():
    with pytest.raises(ValidationError):
        parse_channel_config({"bot_token_ref": "channel/tg/bot-token"})


def test_default_agent_defaults_to_managed_agent():
    # The builtin chat agent is retired; channels default to a managed
    # agent. The default must be the provider key ("claude_code", underscore) —
    # the same key the chat AgentProviderRegistry resolves a turn by — not the
    # "claude-code" resource name, which would fail with UNKNOWN_AGENT at turn time.
    cfg = parse_channel_config(TELEGRAM_CONFIG)
    assert cfg.default_agent == "claude_code"
    assert cfg.default_agent_config is None
    seatalk = parse_channel_config(SEATALK_CONFIG)
    assert seatalk.default_agent == "claude_code"


def test_default_agent_override_kept():
    cfg = parse_channel_config(
        {**TELEGRAM_CONFIG, "default_agent": "claude", "default_agent_config": {"model": "opus"}}
    )
    assert cfg.default_agent == "claude"
    assert cfg.default_agent_config == {"model": "opus"}


def test_group_gating_flags_default_on_both_channel_types():
    """FR-035: require_mention defaults on (group @mention required), and
    ignore_other_mentions defaults off (opt-in), on both channel types."""
    tg = parse_channel_config(TELEGRAM_CONFIG)
    assert tg.require_mention is True
    assert tg.ignore_other_mentions is False
    st = parse_channel_config(SEATALK_CONFIG)
    assert st.require_mention is True
    assert st.ignore_other_mentions is False


def test_group_gating_flags_are_configurable():
    cfg = parse_channel_config(
        {**TELEGRAM_CONFIG, "require_mention": False, "ignore_other_mentions": True}
    )
    assert cfg.require_mention is False
    assert cfg.ignore_other_mentions is True


def test_raw_telegram_token_in_bot_token_ref_rejected():
    raw_token = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    with pytest.raises(ValidationError, match="looks like a raw secret"):
        parse_channel_config({**TELEGRAM_CONFIG, "bot_token_ref": raw_token})


def test_bearer_prefixed_ref_rejected():
    with pytest.raises(ValidationError, match="looks like a raw secret"):
        parse_channel_config({**TELEGRAM_CONFIG, "bot_token_ref": "Bearer abc123"})


def test_bearer_rejection_is_case_insensitive():
    with pytest.raises(ValidationError, match="looks like a raw secret"):
        parse_channel_config({**TELEGRAM_CONFIG, "bot_token_ref": "bearer abc123"})


def test_long_high_entropy_blob_rejected():
    blob = "A1b2C3d4" * 6  # 48 chars, [A-Za-z0-9]+ only
    with pytest.raises(ValidationError, match="looks like a raw secret"):
        parse_channel_config({**TELEGRAM_CONFIG, "bot_token_ref": blob})


def test_seatalk_secret_refs_reject_raw_secrets():
    blob = "A1b2C3d4" * 6
    with pytest.raises(ValidationError, match="looks like a raw secret"):
        parse_channel_config({**SEATALK_CONFIG, "app_secret_ref": blob})
    with pytest.raises(ValidationError, match="looks like a raw secret"):
        parse_channel_config({**SEATALK_CONFIG, "signing_secret_ref": "Bearer xyz"})


def test_normal_path_style_refs_accepted():
    cfg = parse_channel_config({**TELEGRAM_CONFIG, "bot_token_ref": "channel/tg/bot-token"})
    assert cfg.bot_token_ref == "channel/tg/bot-token"


def test_long_path_style_ref_accepted():
    """The blob heuristic excludes "/": path-style refs of any length are
    valid (the UI builds refs like channel/<name>/bot-token from names up
    to 64 chars)."""
    long_ref = "channel/telegram/personal-assistant-bot/bot-token"
    assert len(long_ref) >= 40
    parsed = parse_channel_config({**TELEGRAM_CONFIG, "bot_token_ref": long_ref})
    assert parsed.bot_token_ref == long_ref


def test_long_slashless_blob_still_rejected():
    blob = "A" * 24 + "b8" * 12  # 48 chars, no path separator
    with pytest.raises(ValidationError, match="looks like a raw secret"):
        parse_channel_config({**TELEGRAM_CONFIG, "bot_token_ref": blob})


def test_empty_ref_rejected_by_length_bound():
    with pytest.raises(ValidationError):
        parse_channel_config({**TELEGRAM_CONFIG, "bot_token_ref": ""})


def test_root_model_round_trips_flat_dict():
    """RootModel: validate a flat dict, dump the same flat dict (plus defaults)."""
    model = ChannelConfigModel.model_validate(TELEGRAM_CONFIG)
    dumped = model.model_dump(mode="json")
    assert dumped == {
        "channel_type": "telegram",
        "bot_token_ref": "channel/tg/bot-token",
        "default_agent": "claude_code",
        "default_agent_config": None,
        "require_mention": True,
        "ignore_other_mentions": False,
    }


def test_root_model_round_trips_seatalk_dict():
    model = ChannelConfigModel.model_validate(SEATALK_CONFIG)
    dumped = model.model_dump(mode="json")
    assert dumped == {
        **SEATALK_CONFIG,
        "default_agent": "claude_code",
        "default_agent_config": None,
        "delivery": "webhook",
        "public_base_url": None,
        "tunnel_token_ref": None,
        "require_mention": True,
        "ignore_other_mentions": False,
    }


def test_root_model_applies_raw_secret_rejection():
    with pytest.raises(ValidationError, match="looks like a raw secret"):
        ChannelConfigModel.model_validate(
            {**TELEGRAM_CONFIG, "bot_token_ref": "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}
        )
