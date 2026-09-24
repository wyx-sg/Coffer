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

from pydantic import (
    BaseModel,
    Field,
    RootModel,
    field_validator,
)

# A credential ref is a vault ADDRESS, not a secret: Coffer mints
# "channel/<uuid4 hex>/<secret>" for one the UI stores, and a user may type a
# path of their own. Raw secrets are longer and machine-shaped; reject the
# obvious cases. The high-entropy pattern deliberately excludes "/": path-style
# refs of any length stay valid, and the Telegram/Bearer patterns still catch
# the secrets users realistically paste here.
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

    # The **uid** of the agent resource this channel drives by default (ADR
    # resource-identity-is-an-immutable-uid). It is a cross-resource reference,
    # so it holds the one thing about that agent the owner cannot change: not
    # its registry name, and not the turn platform's agent key either. The key
    # is derived from this at the one place the turn platform needs it (the
    # runtime gate in ``application/channel/wanted.py``), which is what let the
    # translation module this field used to need be deleted outright.
    #
    # There is NO default value, because there is nothing a schema could name:
    # a uid is minted per vault, so no constant can stand for "the usual
    # agent". ``None`` therefore means exactly what it says — this channel is
    # bound to no agent — and a channel in that state drives nothing and is not
    # started. That is a visible, fail-closed state, not a silent fallback to
    # whichever agent happened to be called ``claude-code``.
    default_agent: str | None = Field(default=None, max_length=64)
    default_agent_config: dict[str, Any] | None = None
    # Group inbound gating ("Configure when the bot answers in a group").
    # ``require_mention`` (default on) keeps the
    # bot silent in a group until @mentioned / replied-to; ``ignore_other_mentions``
    # (opt-in) drops a group message that @mentions any non-bot user, even when
    # it also mentions the bot, so the bot never butts into human-aimed traffic.
    require_mention: bool = True
    ignore_other_mentions: bool = False
    # NOTE: a channel curates no MODELS. A new conversation opens on the bound
    # agent's own CLI default and ``/model`` offers that agent's whole
    # catalogue, refusing nothing — picking a model is the agent's business,
    # and the channel is not a second place to narrow what a given agent may
    # run. WHICH agents the channel may drive is a different question and is
    # the channel's own: it is the framework-level per-agent scope on the
    # resource row (ADR per-agent-resource-scope), not a config field.
    #
    # The ``machine_id`` (spec vault-sync "Derive machine identity from the host") of the ONE
    # machine whose daemon starts this channel's adapter. A channel travels
    # again — it is an ordinary synced resource document — and this field is
    # what makes that safe: a bot identity tolerates a single consumer, so the
    # document says which machine that is and every other machine reads its own
    # id, finds it does not match, and starts nothing. See spec channels
    # "Bind each channel to the one machine that runs it".
    #
    # It lives in ``config`` and not on the resource row because it travels:
    # ``config`` is what a resource document carries, while the row's reach
    # (``enabled`` + ``scope``) is deliberately left behind on each machine.
    # The two answer different questions and the spec keeps them apart — reach
    # is *which agents*, here; the binding is *which machine* runs the adapter,
    # for the whole vault.
    #
    # ``None`` is unbound, and unbound runs NOWHERE. It is not "runs here": a
    # document with no machine named in it means the same thing on every
    # machine that holds it, and "start it" would mean "start it on all of
    # them" — the rival-consumer failure this field exists to prevent. The
    # surfaces show an unbound channel as unbound and bind it in one click.
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
    # SeaTalk inbound has one transport: the outbound websocket connection the
    # daemon holds (spec channels/seatalk "Receive every event over one
    # outbound websocket connection"). Its register handshake authenticates
    # from exactly these two values, so the configuration carries nothing
    # else — no delivery switch, no signing secret, no public URL, no tunnel.
    # A stored document still carrying those webhook-era keys (a second
    # machine on an older build) is read cleanly: unknown keys are ignored,
    # as for every channel config.

    @field_validator("app_secret_ref")
    @classmethod
    def _ref_not_secret(cls, v: str) -> str:
        return _reject_raw_secret("app_secret_ref", v)


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
