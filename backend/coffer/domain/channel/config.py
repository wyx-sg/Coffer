"""Channel configuration value objects.

`ChannelConfig` is what `Resource.config` holds when `kind == "channel"`.
Telegram + SeaTalk as a Pydantic discriminated union on `channel_type`.

Secrets never live here: every `*_ref` field is a credential-store ref. A
value that *looks* like the raw secret itself (a Telegram bot token, a long
high-entropy blob) is rejected with a pointer at the credential store.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    Field,
    RootModel,
    field_validator,
)

# A credential ref is a human-chosen path like "channel/tg/bot-token".
# Raw secrets are longer and machine-shaped; reject the obvious cases. The
# high-entropy pattern deliberately excludes "/": path-style refs of any
# length stay valid, and the Telegram/Bearer patterns still catch the
# secrets users realistically paste here.
_RAW_SECRET_PATTERNS = [
    re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$"),  # Telegram bot token
    re.compile(r"^[A-Za-z0-9+=_-]{40,}$"),  # long high-entropy blob (no path separator)
    re.compile(r"^Bearer\s+", re.IGNORECASE),
]


def _reject_raw_secret(field: str, value: str) -> str:
    for pat in _RAW_SECRET_PATTERNS:
        if pat.search(value):
            raise ValueError(
                f"{field} looks like a raw secret; store the secret with "
                f"`coffer credentials set <ref>` and put the ref here instead"
            )
    return value


class _CommonChannelFields(BaseModel):
    """Fields shared by every channel type: the agent it routes to by default."""

    # The provider key the chat AgentProviderRegistry resolves a turn by
    # (underscore form), NOT the "claude-code" resource name — a hyphenated
    # value reaches turn time and fails with UNKNOWN_AGENT.
    default_agent: str = "claude_code"
    default_agent_config: dict[str, Any] | None = None
    # Group inbound gating (FR-035). ``require_mention`` (default on) keeps the
    # bot silent in a group until @mentioned / replied-to; ``ignore_other_mentions``
    # (opt-in) drops a group message that @mentions any non-bot user, even when
    # it also mentions the bot, so the bot never butts into human-aimed traffic.
    require_mention: bool = True
    ignore_other_mentions: bool = False
    # DEPRECATED / INERT (ADR-045 amendment, spec 009): superseded by the
    # framework-level machine x agent `scope` column on the resource itself
    # (see coffer.domain.scope, coffer.domain.resource.Resource.scope).
    # ChannelRuntime no longer reads this field — it consults `scope` via
    # `machine_in_scope`. Kept in the schema (not removed) purely so old
    # config payloads / docs referencing it still validate; a migration
    # (0047) backfills `scope` from whatever value this held at upgrade time.
    # Was: the machine_id of the ONE machine whose runtime starts this
    # channel's adapter — a bot identity polled (or a webhook received) from
    # two synced machines at once would fight over the platform. None = not
    # started anywhere until the user picks a machine.
    runs_on: str | None = Field(default=None, max_length=64)


class TelegramChannelConfig(_CommonChannelFields):
    channel_type: Literal["telegram"] = "telegram"
    bot_token_ref: str = Field(min_length=1, max_length=256)

    @field_validator("bot_token_ref")
    @classmethod
    def _ref_not_secret(cls, v: str) -> str:
        return _reject_raw_secret("bot_token_ref", v)


class SeaTalkChannelConfig(_CommonChannelFields):
    channel_type: Literal["seatalk"] = "seatalk"
    app_id: str = Field(min_length=1, max_length=128)
    app_secret_ref: str = Field(min_length=1, max_length=256)
    signing_secret_ref: str = Field(min_length=1, max_length=256)
    # The tunnel's public base URL (scheme://host[:port]); the full SeaTalk
    # callback URL is this + "/seatalk/<name>". Optional: until the user records
    # their public base URL here we only know the loopback address.
    public_base_url: str | None = Field(default=None, max_length=512)
    # Credential-store ref for a cloudflared connector token. When set, the
    # daemon runs and supervises a `cloudflared tunnel run` child for this
    # channel (a managed named tunnel); absent means the user runs their own.
    tunnel_token_ref: str | None = Field(default=None, max_length=256)

    @field_validator("app_secret_ref", "signing_secret_ref", "tunnel_token_ref")
    @classmethod
    def _ref_not_secret(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _reject_raw_secret("secret ref", v)

    @field_validator("public_base_url")
    @classmethod
    def _normalize_public_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        parsed = urlparse(v)
        if parsed.scheme != "https":
            raise ValueError("public_base_url must start with https:// (SeaTalk requires HTTPS)")
        if not parsed.netloc:
            raise ValueError("public_base_url must include a host, e.g. https://example.com")
        if parsed.path.strip("/") or parsed.query or parsed.fragment:
            raise ValueError(
                "public_base_url must be a bare base URL (scheme://host) with no path; "
                "Coffer appends /seatalk/<name> itself"
            )
        return v.rstrip("/")


ChannelConfig = Annotated[
    TelegramChannelConfig | SeaTalkChannelConfig,
    Field(discriminator="channel_type"),
]


class ChannelConfigModel(RootModel[ChannelConfig]):
    """RootModel wrapper so the resource framework's `config_schema`
    (a single BaseModel) can carry the discriminated union: validation
    accepts the flat config dict and `model_dump` returns it unchanged."""


def parse_channel_config(config: dict[str, Any]) -> TelegramChannelConfig | SeaTalkChannelConfig:
    """Validate a raw resource config dict into the typed union member.

    Single validation entry point: the same RootModel the resource framework
    uses, so registration-time and adapter-start-time validation can never
    diverge.
    """
    return ChannelConfigModel.model_validate(config).root
