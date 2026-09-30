"""Which top-level config keys a kind's ``config_schema`` reads (spec
vault-storage "Keep every vault document a JSON object that preserves what it
does not know").

The vault's resource rule refuses a file whose config holds any other key,
one finding per key, so a person sees each key by name rather than one
schema error.

A plain model reads its fields (by name and alias); one with
``extra="allow"`` reads every key (``None``). A model that ignores extras
still reads only its fields, so a key it would drop silently is refused too.
A ``RootModel`` over a union — a
channel's config, discriminated by ``channel_type`` — reads the keys of the
member the config is; the member is the one that accepts the config's own
keys, and when none does, the union of every member's keys is what is known.
"""

from __future__ import annotations

import types
import typing
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, RootModel, ValidationError


def _members(schema: type[BaseModel]) -> list[type[BaseModel]] | None:
    """The models a ``RootModel``'s root may be; ``None`` for any other root."""
    annotation: Any = schema.model_fields["root"].annotation
    while typing.get_origin(annotation) is typing.Annotated:
        annotation = typing.get_args(annotation)[0]
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation) if origin in (typing.Union, types.UnionType) else ()
    candidates = list(args) if args else [annotation]
    members = [a for a in candidates if isinstance(a, type) and issubclass(a, BaseModel)]
    return members if members and len(members) == len(candidates) else None


def _fields(model: type[BaseModel]) -> frozenset[str] | None:
    if model.model_config.get("extra") == "allow":
        return None
    keys: set[str] = set()
    for name, info in model.model_fields.items():
        keys.add(name)
        if info.alias:
            keys.add(info.alias)
        if isinstance(info.validation_alias, str):
            keys.add(info.validation_alias)
    return frozenset(keys)


def known_keys(
    schema: type[BaseModel] | None, config: Mapping[str, Any] | None = None
) -> frozenset[str] | None:
    """The top-level keys of ``config`` that ``schema`` reads; ``None`` means
    every key (no schema, or one that never refuses a key)."""
    if schema is None:
        return None
    if not issubclass(schema, RootModel):
        return _fields(schema)
    members = _members(schema)
    if members is None:
        return None
    known = [_fields(m) for m in members]
    if any(k is None for k in known):
        return None
    keys = [k for k in known if k is not None]
    for member, member_keys in zip(members, keys, strict=True):
        subset = {k: v for k, v in (config or {}).items() if k in member_keys}
        try:
            member.model_validate(subset)
        except ValidationError:
            continue
        return member_keys
    return frozenset().union(*keys)


__all__ = ["known_keys"]
