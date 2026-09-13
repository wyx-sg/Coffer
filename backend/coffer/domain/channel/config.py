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
    model_validator,
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
    # NOTE: a channel curates no models. A new conversation opens on the bound
    # agent's own CLI default and ``/model`` offers that agent's whole
    # catalogue, refusing nothing — the channel is a route to an agent, not a
    # second place to narrow what that agent may run.
    #
    # NOTE: there is no runtime-affinity field here any more. `runs_on` (the
    # machine whose runtime started this channel's adapter) went away with
    # continuous multi-machine sync (ADR vault-export-import) — an enabled channel runs on
    # this, the only, machine. Pydantic ignores unknown keys, so a stored
    # pre-withdrawal config carrying `runs_on` still validates.


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
    # FR-071: how SeaTalk delivers this bot's events. "webhook" is the HTTPS
    # Event Callback — a public URL the platform POSTs to, which needs a signing
    # secret and some form of ingress. "websocket" is the platform's WebSocket
    # Event Callback: the bot holds one outbound connection and needs no public
    # URL at all. SeaTalk allows exactly one method per bot at a time, so this
    # is a choice, never a pair.
    #
    # The default is "webhook" because that is what every channel configured
    # before this field existed actually is — the absent key already describes
    # the stored reality, so nothing is being reinterpreted and no migration is
    # needed.
    delivery: Literal["webhook", "websocket"] = "webhook"
    # Credential-store ref for the callback signing secret. Required on webhook
    # delivery (the listener verifies every POST with it); forbidden on
    # websocket delivery, where the register handshake authenticates the
    # connection and nothing is ever signed.
    signing_secret_ref: str | None = Field(default=None, min_length=1, max_length=256)
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

    @model_validator(mode="after")
    def _delivery_decides_which_fields_exist(self) -> SeaTalkChannelConfig:
        """FR-071: each delivery method owns a disjoint set of fields.

        A field that decides nothing is a lie about the system, so a websocket
        channel may not carry a signing secret, a public base URL or a tunnel
        token — none of them is consulted on that path, and leaving them behind
        would make the channel look like it still has webhook ingress. Switching
        an existing channel between methods therefore clears the other method's
        fields. That is honest: the switch is never free anyway, because the
        delivery method is also a per-bot setting on SeaTalk's Developer Portal
        and has to be changed there in step.

        ``app_id`` / ``app_secret_ref`` stay required on both — the websocket
        register handshake authenticates with exactly those.
        """
        if self.delivery == "webhook":
            if not self.signing_secret_ref:
                raise ValueError(
                    "signing_secret_ref is required when delivery is 'webhook': "
                    "SeaTalk signs every callback POST and the listener verifies it"
                )
            return self
        forbidden = [
            name
            for name, value in (
                ("signing_secret_ref", self.signing_secret_ref),
                ("public_base_url", self.public_base_url),
                ("tunnel_token_ref", self.tunnel_token_ref),
            )
            if value
        ]
        if forbidden:
            raise ValueError(
                f"{', '.join(forbidden)} must be empty when delivery is 'websocket': "
                "a websocket channel has no public callback URL to describe, no "
                "tunnel to manage and nothing signed to verify"
            )
        return self


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
