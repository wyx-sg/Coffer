"""Which config keys a kind's schema reads (coffer.domain.vault.config_keys):
the store hands a kind only those and keeps the rest in the file."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from coffer.domain.channel.config import ChannelConfigModel
from coffer.domain.vault.config_keys import known_keys


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    colour: str
    shade: str = Field(default="", alias="tone")


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")
    colour: str = ""


class _A(BaseModel):
    kind: Literal["a"]
    left: str = ""


class _B(BaseModel):
    kind: Literal["b"]
    right: str = ""


class _Union(RootModel[Annotated[_A | _B, Field(discriminator="kind")]]):
    pass


def test_a_plain_model_reads_its_fields_and_aliases() -> None:
    assert known_keys(_Strict) == {"colour", "shade", "tone"}
    assert known_keys(_Open) is None
    assert known_keys(None) is None


def test_a_union_reads_the_keys_of_the_member_the_config_is() -> None:
    assert known_keys(_Union, {"kind": "a", "left": "x", "newer": 1}) == {"kind", "left"}
    assert known_keys(_Union, {"kind": "b", "right": "y"}) == {"kind", "right"}
    # No member accepts it: every member's keys are known.
    assert known_keys(_Union, {"kind": "c"}) == {"kind", "left", "right"}


def test_a_channel_config_keeps_its_discriminator() -> None:
    config = {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-token"}
    known = known_keys(ChannelConfigModel, config)
    assert known is not None and {"channel_type", "bot_token_ref"} <= known
