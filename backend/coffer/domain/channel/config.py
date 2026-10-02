"""Channel configuration value objects.

`ChannelConfig` is what `Resource.config` holds when `kind == "channel"`.
Telegram + SeaTalk as a Pydantic discriminated union on `channel_type`.

Secrets never live here: every `*_ref` field is a secret-store ref. A
value that *looks* like the raw secret itself (a Telegram bot token, a long
high-entropy blob) is rejected with a pointer at the secret store.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
)

# A secret ref is a vault ADDRESS, not a secret: Coffer mints
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
                f"`coffer secret set <ref>` and put the ref here instead"
            )
    return value


class _CommonChannelFields(BaseModel):
    """Fields shared by every channel type: the agent it routes to by default."""

    # A key no channel type declares is refused, as for every kind's config,
    # so a retired field (SeaTalk's webhook-era delivery keys) cannot linger
    # in a stored config unnoticed.
    model_config = ConfigDict(extra="forbid")

    # The **uid** of the agent resource this channel drives by default (ADR
    # identity-is-the-uid-inside-the-file). It is a cross-resource reference,
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
    # The quiet windows of "Take a burst of messages as one turn", in seconds: how
    # long to wait after a text message, and after a forwarded record or files with
    # no text, before the held burst runs. 0 runs every message as its own turn.
    wait_after_text_seconds: float = Field(default=1.5, ge=0, le=60)
    wait_after_forward_seconds: float = Field(default=5.0, ge=0, le=60)
    # "Show a turn's working state as one status line": whether the live status
    # lists the turn's step lines under its header. Off keeps the header (time,
    # step count) and the narration line and hides the steps — e.g. in a group.
    show_steps: bool = True
    # "Ping the asker when a long turn ends": a turn that ran at least this many
    # seconds ends with one short completion line where its answer would not
    # notify on its own. 0 turns the ping off.
    notify_after_seconds: float = Field(default=90.0, ge=0, le=3600)
    # "Open a new conversation after an idle period": a chat whose active
    # conversation has been idle longer than this many hours opens a NEW
    # conversation on the owner's next message (the old one stays in the list).
    # 0 never rolls a conversation over.
    new_conversation_after_idle_hours: float = Field(default=24.0, ge=0, le=8760)
    # The working directories `/dir` may switch a conversation into (spec
    # channels "Choose the working directory from chat"): absolute paths, each
    # also admitting the directories beneath it. Empty means the channel's
    # default directory is the only one — a chat cannot point an agent at an
    # arbitrary folder on this machine.
    directories: list[str] = Field(default_factory=list, max_length=32)
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

    @field_validator("default_agent_config")
    @classmethod
    def _absolute_default_directory(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        # ``cwd`` here is the channel's default working directory: where its new
        # conversations start (spec channels "Choose the working directory from chat").
        cwd = (v or {}).get("cwd")
        if cwd is not None and (not isinstance(cwd, str) or not cwd.startswith("/")):
            raise ValueError(f"the default directory must be an absolute path; got {cwd!r}")
        return v

    @field_validator("directories")
    @classmethod
    def _absolute_directories(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in v:
            path = raw.strip()
            if not path.startswith("/") or len(path) > 1024:
                raise ValueError(f"directories must be absolute paths; got {raw!r}")
            path = path.rstrip("/") or "/"
            if path not in cleaned:
                cleaned.append(path)
        return cleaned


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
