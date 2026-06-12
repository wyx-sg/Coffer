"""make_channel_kind: Kind wiring + credential-ref extraction."""

from __future__ import annotations

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
