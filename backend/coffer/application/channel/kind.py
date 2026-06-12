"""Channel-specific Kind wiring used by the composition root."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.domain.channel.config import ChannelConfigModel
from coffer.domain.resource import Kind, ResourceRef

_REF_FIELDS = ("bot_token_ref", "app_secret_ref", "signing_secret_ref")


def _channel_credential_ref_extractor(config: dict[str, Any]) -> dict[str, str]:
    """Every `*_ref` field is a credential ref to probe before registration."""
    refs: dict[str, str] = {}
    for field in _REF_FIELDS:
        value = config.get(field)
        if isinstance(value, str) and value:
            refs[field] = value
    return refs


def make_channel_kind(on_delete: Callable[[ResourceRef], Awaitable[None]] | None = None) -> Kind:
    """Construct the `channel` Kind.

    ``on_delete`` is injected by the composition root: it evicts the channel
    from the runtime (stopping its adapter and, when it was the last SeaTalk
    channel, the callback listener) before the row — and, via FK cascade, the
    peer binding — is removed. Channel config holds only credential refs, so
    no audit redaction is needed.
    """
    return Kind(
        name="channel",
        display_name="Channel",
        config_schema=ChannelConfigModel,
        on_delete=on_delete,
        credential_ref_extractor=_channel_credential_ref_extractor,
    )
