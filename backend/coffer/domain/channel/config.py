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

#: Shape-only bounds for the channel's allowed model range. Model ids are
#: OPAQUE — they are handed to the agent's CLI verbatim and Coffer writes down
#: no model name of its own — so the only checks are that an id is a non-blank
#: string, that the list holds no duplicates, and that neither the list nor an
#: entry is absurdly long.
_MAX_MODELS = 200
_MAX_MODEL_ID_LEN = 200

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
    # Model curation belongs to the CHANNEL, not to the agent it routes to. The
    # agent resource governs what a person gets when they open that agent
    # directly; a channel is its own place with its own audience, and these two
    # fields are how it says so.
    #
    # ``default_model`` is what a NEW conversation on this channel opens on.
    # ``None`` pins nothing and the agent's CLI default applies — which is the
    # behaviour of every channel nobody has configured.
    default_model: str | None = Field(default=None, max_length=_MAX_MODEL_ID_LEN)
    # ``models`` is the channel's allowed RANGE: the ``/model`` card offers
    # exactly these, and ``/model <id>`` refuses anything else. EMPTY means NOT
    # CURATED — every model the bound agent offers is allowed — never "no
    # models", so an unconfigured channel behaves exactly as it did before.
    models: list[str] = Field(default_factory=list)
    # NOTE: there is no runtime-affinity field here any more. `runs_on` (the
    # machine whose runtime started this channel's adapter) went away with
    # continuous multi-machine sync (ADR vault-export-import) — an enabled channel runs on
    # this, the only, machine. Pydantic ignores unknown keys, so a stored
    # pre-withdrawal config carrying `runs_on` still validates.

    @field_validator("default_model")
    @classmethod
    def _clean_default_model(cls, v: str | None) -> str | None:
        """Blank is the same as unset — a cleared text field must not pin the
        empty string as a model name."""
        if v is None:
            return None
        model = v.strip()
        return model or None

    @field_validator("models")
    @classmethod
    def _well_formed_models(cls, v: list[str]) -> list[str]:
        """Shape only: non-blank ids, no duplicates, sane bounds. Whether an id
        is one the bound agent can actually run is the agent's answer, not ours
        — an allowed range is a statement of intent, and an id the next CLI
        release drops is a stale menu entry, not a config error."""
        if len(v) > _MAX_MODELS:
            raise ValueError(f"too many models: at most {_MAX_MODELS}")
        cleaned: dict[str, None] = {}
        for m in v:
            model = m.strip()
            if not model:
                raise ValueError("model id must not be empty")
            if len(model) > _MAX_MODEL_ID_LEN:
                raise ValueError(f"model id too long: at most {_MAX_MODEL_ID_LEN} characters")
            cleaned.setdefault(model, None)
        return list(cleaned)

    @model_validator(mode="after")
    def _default_model_within_range(self) -> _CommonChannelFields:
        """A channel cannot start conversations on a model it then refuses.

        Only checked when the range is curated: with ``models`` empty there is
        no range to be outside of, and ``default_model`` is free text handed to
        the CLI verbatim.
        """
        if self.default_model is None or not self.models:
            return self
        if self.default_model not in self.models:
            raise ValueError(
                f"default_model {self.default_model!r} is not in this channel's "
                f"allowed models ({', '.join(self.models)}); add it there or "
                f"clear default_model"
            )
        return self


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
