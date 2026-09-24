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
}

_WEBHOOK_ERA_KEYS = {
    "delivery": "webhook",
    "signing_secret_ref": "channel/st/signing-secret",
    "public_base_url": "https://x.example.com",
    "tunnel_token_ref": "channel/st/tunnel-token",
}


def test_a_seatalk_config_is_its_app_credentials_and_nothing_inbound():
    """SeaTalk inbound has one transport, so the config carries no field that
    chooses or configures one (spec channels/seatalk "Configure a SeaTalk
    channel by app id and secret reference")."""
    fields = set(SeaTalkChannelConfig.model_fields)
    assert {"app_id", "app_secret_ref"} <= fields
    assert not fields & set(_WEBHOOK_ERA_KEYS)


def test_a_document_still_carrying_webhook_era_keys_is_read_cleanly():
    """A second machine on an older build may still publish them; they are
    ignored like any unknown key and never come back out of a dump."""
    cfg = parse_channel_config({**SEATALK_CONFIG, **_WEBHOOK_ERA_KEYS})
    assert isinstance(cfg, SeaTalkChannelConfig)
    dumped = cfg.model_dump(mode="json")
    assert not set(dumped) & set(_WEBHOOK_ERA_KEYS)


@pytest.mark.parametrize("missing", ["app_id", "app_secret_ref"])
def test_seatalk_requires_app_id_and_secret_ref(missing: str):
    with pytest.raises(ValidationError):
        parse_channel_config({k: v for k, v in SEATALK_CONFIG.items() if k != missing})


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


def test_channel_type_discriminates_union():
    """The same extra fields land on the model picked by channel_type."""
    cfg = parse_channel_config({**SEATALK_CONFIG})
    assert isinstance(cfg, SeaTalkChannelConfig)
    with pytest.raises(ValidationError):
        parse_channel_config({"channel_type": "slack", "bot_token_ref": "a/b"})


def test_missing_channel_type_rejected():
    with pytest.raises(ValidationError):
        parse_channel_config({"bot_token_ref": "channel/tg/bot-token"})


def test_a_channel_names_no_agent_until_its_owner_picks_one():
    # ``default_agent`` holds the UID of an agent resource (ADR
    # resource-identity-is-an-immutable-uid), and there is no constant a schema
    # could default it to: a uid is minted per vault. So the absent value is
    # ``None`` — bound to nobody — and not a guess at which agent the owner
    # meant. The runtime refuses to start such a channel rather than routing it
    # somewhere it was never told to.
    cfg = parse_channel_config(TELEGRAM_CONFIG)
    assert cfg.default_agent is None
    assert cfg.default_agent_config is None
    seatalk = parse_channel_config(SEATALK_CONFIG)
    assert seatalk.default_agent is None


def test_default_agent_override_kept():
    cfg = parse_channel_config(
        {
            **TELEGRAM_CONFIG,
            "default_agent": "9f2c1b7a4e8d4c3f9a0b5d6e7f801234",
            "default_agent_config": {"model": "opus"},
        }
    )
    assert cfg.default_agent == "9f2c1b7a4e8d4c3f9a0b5d6e7f801234"
    assert cfg.default_agent_config == {"model": "opus"}


def test_group_gating_flags_default_on_both_channel_types():
    """require_mention defaults on (group @mention required), and
    ignore_other_mentions defaults off (opt-in), on both channel types (spec
    channels "Configure when the bot answers in a group")."""
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
        parse_channel_config({**SEATALK_CONFIG, "app_secret_ref": "Bearer xyz"})


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
        "default_agent": None,
        "default_agent_config": None,
        "require_mention": True,
        "ignore_other_mentions": False,
        "runs_on": None,
    }


def test_root_model_round_trips_seatalk_dict():
    model = ChannelConfigModel.model_validate(SEATALK_CONFIG)
    dumped = model.model_dump(mode="json")
    assert dumped == {
        **SEATALK_CONFIG,
        "default_agent": None,
        "default_agent_config": None,
        "require_mention": True,
        "ignore_other_mentions": False,
        "runs_on": None,
    }


def test_the_binding_is_an_ordinary_config_field():
    """``runs_on`` travels inside the config, so it must survive a round trip.

    The whole design rests on this: the binding is carried by the resource
    DOCUMENT, which is identity plus description plus config, and a field that
    did not survive validation would be a binding that quietly reset itself
    every time another machine applied the document.
    """
    parsed = parse_channel_config({**TELEGRAM_CONFIG, "runs_on": "a1b2c3d4e5f60718"})
    assert parsed.runs_on == "a1b2c3d4e5f60718"
    assert parse_channel_config(TELEGRAM_CONFIG).runs_on is None


def test_root_model_applies_raw_secret_rejection():
    with pytest.raises(ValidationError, match="looks like a raw secret"):
        ChannelConfigModel.model_validate(
            {**TELEGRAM_CONFIG, "bot_token_ref": "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}
        )
