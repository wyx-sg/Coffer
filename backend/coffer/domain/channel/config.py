"""Channel configuration value objects.

`ChannelConfig` is what `Resource.config` holds when `kind == "channel"`.
Telegram + SeaTalk as a Pydantic discriminated union on `channel_type`.

Secrets never live here: every `*_ref` field is a credential-store ref. A
value that *looks* like the raw secret itself (a Telegram bot token, a long
high-entropy blob) is rejected with a pointer at the credential store.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, RootModel, field_validator, model_validator

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


class Workspace(BaseModel):
    """A named, pre-authorized working directory an agent may run in when
    chosen from this channel. The set of workspaces is the cwd allowlist: a
    channel never honors a bare path typed into a chat message."""

    name: str = Field(min_length=1, max_length=64)
    path: str = Field(min_length=1, max_length=4096)

    @field_validator("path")
    @classmethod
    def _path_absolute(cls, v: str) -> str:
        if not (PurePosixPath(v).is_absolute() or PureWindowsPath(v).is_absolute()):
            raise ValueError("workspace path must be absolute")
        return v


class _CommonChannelFields(BaseModel):
    """Fields shared by every channel type: the agent it routes to by default
    and the workspace allowlist used when routing to a bridged agent."""

    default_agent: str = "claude_code"
    default_agent_config: dict[str, Any] | None = None
    workspaces: list[Workspace] = Field(default_factory=list)
    default_workspace: str | None = None

    @model_validator(mode="after")
    def _check_workspaces(self) -> _CommonChannelFields:
        names = [w.name for w in self.workspaces]
        if len(names) != len(set(names)):
            raise ValueError("duplicate workspace name")
        if self.default_workspace is not None and self.default_workspace not in names:
            raise ValueError("default_workspace must name a declared workspace")
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

    @field_validator("app_secret_ref", "signing_secret_ref")
    @classmethod
    def _ref_not_secret(cls, v: str) -> str:
        return _reject_raw_secret("secret ref", v)


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
