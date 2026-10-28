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
    model_validator,
)

from coffer.domain.chat.channel_prompt import default_reply_style, reply_style_hash

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
                f"{field} looks like a raw secret; store the secret on the "
                f"Secrets page (or `coffer secret set <ref>`) and put the ref here instead"
            )
    return value


#: Keys a channel config used to carry and no longer does. A stored document
#: may still hold them; they are dropped on read rather than refused, so an
#: upgrade never stops a channel from starting.
_RETIRED_KEYS = frozenset({"notify_after_seconds"})

#: The longest reply style a channel keeps per chat kind (spec channels "Let the
#: owner rewrite a channel's reply style"). It rides on every turn, so it is
#: capped well below anything that would crowd the agent's own context — and
#: above Coffer's default plus a 4,000-character prompt of the kind that the
#: style replaced, so every migrated channel fits.
REPLY_STYLE_MAX_LENGTH = 6000

#: The owner prompts a channel carried before the reply style replaced them
#: (ADR channel-prompt-fixed-note-and-editable-style), and the style
#: each one migrates into.
_LEGACY_PROMPT_KEYS = {"direct_system_prompt": "direct", "group_system_prompt": "group"}


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
    # "Let others in a group ask the bot": in a group an owner has registered,
    # anyone else who @mentions the bot gets an answer, read-only — questions
    # and checks, never a change or a task. Off, only owners are answered.
    others_can_ask: bool = True
    # The quiet windows of "Take a burst of messages as one turn", in seconds: how
    # long to wait after a text message, and after a forwarded record or files with
    # no text, before the held burst runs. 0 runs every message as its own turn.
    wait_after_text_seconds: float = Field(default=1.5, ge=0, le=60)
    wait_after_forward_seconds: float = Field(default=5.0, ge=0, le=60)
    # "Show a turn's working state as one status line": whether the live status
    # lists the turn's step lines under its header. Off keeps the header (time,
    # step count) and the narration line and hides the steps — e.g. in a group.
    show_steps: bool = True
    # "Open a new conversation after an idle period": a direct chat, or a group
    # whose main chat is one conversation, whose active conversation has been
    # idle longer than this many hours opens a NEW conversation on the owner's
    # next message (the old one stays in the list). A thread — group thread,
    # forum topic, parallel thread — never rolls over. 0 never rolls over.
    new_conversation_after_idle_hours: float = Field(default=24.0, ge=0, le=8760)
    # The working directories `/dir` may switch a conversation into (spec
    # channels "Choose the working directory from chat"): absolute paths, each
    # also admitting the directories beneath it. Empty means the channel's
    # default directory is the only one — a chat cannot point an agent at an
    # arbitrary folder on this machine.
    directories: list[str] = Field(default_factory=list, max_length=32)
    # The owner's rewrite of the reply style (spec channels "Let the owner rewrite
    # a channel's reply style"): for a direct chat (and its threads), and for a
    # group's main chat and its threads. Empty follows Coffer's default, which
    # is also what text equal to that default is stored as. It follows Coffer's
    # fixed channel note on every turn and never replaces it.
    direct_reply_style: str = Field(default="", max_length=REPLY_STYLE_MAX_LENGTH)
    group_reply_style: str = Field(default="", max_length=REPLY_STYLE_MAX_LENGTH)
    # The fingerprint of Coffer's default each rewrite was written against
    # (``reply_style_hash``), so the page can say the default has changed
    # since. "" while the style follows the default.
    direct_reply_style_base: str = Field(default="", max_length=64)
    group_reply_style_base: str = Field(default="", max_length=64)
    # NOTE: a channel curates no MODELS. A new conversation opens on the bound
    # agent's own CLI default and ``/model`` offers that agent's whole
    # catalogue, refusing nothing — picking a model is the agent's business,
    # and the channel is not a second place to narrow what a given agent may
    # run. WHICH agents the channel may drive is a different question and is
    # the channel's own: it is the framework-level per-agent scope on the
    # resource row (ADR per-agent-resource-scope), not a config field.

    @model_validator(mode="before")
    @classmethod
    def _drop_retired_keys(cls, data: Any) -> Any:
        """Migrations on read (the file loses the old keys on its next write).

        - The long-turn ping is gone: drop ``notify_after_seconds``.
        - The owner prompt became the reply style: a stored
          ``direct_system_prompt`` / ``group_system_prompt`` was appended after
          Coffer's whole note, so it becomes a rewrite holding Coffer's default
          style followed by the owner's text — the agent reads the same
          instructions as before. An empty one simply goes.
        """
        if not isinstance(data, dict):
            return data
        if not any(k in data for k in _RETIRED_KEYS | _LEGACY_PROMPT_KEYS.keys()):
            return data
        out = {k: v for k, v in data.items() if k not in _RETIRED_KEYS | _LEGACY_PROMPT_KEYS.keys()}
        for key, kind in _LEGACY_PROMPT_KEYS.items():
            old = data.get(key)
            # A document that already says what the style is (even "") wins.
            if not isinstance(old, str) or not old.strip() or f"{kind}_reply_style" in out:
                continue
            default = default_reply_style(kind)
            out[f"{kind}_reply_style"] = f"{default}\n\n{old.strip()}"
            out[f"{kind}_reply_style_base"] = reply_style_hash(default)
        return out

    @field_validator("default_agent_config")
    @classmethod
    def _absolute_default_directory(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        # ``cwd`` here is the channel's default working directory: where its new
        # conversations start (spec channels "Choose the working directory from chat").
        cwd = (v or {}).get("cwd")
        if cwd is not None and (not isinstance(cwd, str) or not cwd.startswith("/")):
            raise ValueError(f"the default directory must be an absolute path; got {cwd!r}")
        return v

    @field_validator("direct_reply_style", "group_reply_style")
    @classmethod
    def _trim_reply_style(cls, v: str) -> str:
        # Surrounding blank lines and spaces carry nothing; a style of only
        # whitespace is no rewrite. The text inside is kept as written.
        return v.strip()

    @model_validator(mode="after")
    def _settle_reply_styles(self) -> Any:
        # A rewrite equal to Coffer's default is no rewrite: it is stored empty,
        # so it keeps following the default. A rewrite saved without saying
        # what it was written against was written against today's default.
        for kind in ("direct", "group"):
            default = default_reply_style(kind)
            style = getattr(self, f"{kind}_reply_style")
            if style == default.strip():
                style = ""
                object.__setattr__(self, f"{kind}_reply_style", "")
            base = getattr(self, f"{kind}_reply_style_base")
            if not style:
                object.__setattr__(self, f"{kind}_reply_style_base", "")
            elif not base:
                object.__setattr__(self, f"{kind}_reply_style_base", reply_style_hash(default))
        return self

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
