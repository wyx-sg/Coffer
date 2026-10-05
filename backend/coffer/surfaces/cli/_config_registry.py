"""The shape of a ``coffer config`` key.

A key names its type, its help, the place that stores it, how to read it, how
to write it and how to return to its default (spec resource-framework "Offer
every management operation on the command line"). Only keys read before the daemon binds are
here, so none of them ever talks to the daemon.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class SettingValueError(ValueError):
    """A value the key's type refuses — raised before anything is written."""


@dataclass
class Reading:
    """One key's current state.

    ``value`` and ``default`` are JSON values (``None`` = nothing chosen).
    ``lines`` replaces the plain value in ``config get``'s human output where a
    key has more to say than its value; ``extra`` joins ``config get --json``.
    """

    value: Any
    default: Any = None
    has_default: bool = True
    note: str | None = None
    lines: list[str] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Setting:
    key: str
    #: The accepted values, as a person reads them.
    type: str
    help: str
    #: Where the setting is kept.
    store: str
    parse: Callable[[str], Any]
    read: Callable[[], Reading]
    write: Callable[[Any], list[str]]
    unset: Callable[[], list[str]]


def show(value: Any) -> str:
    """A JSON value as a person reads it."""
    if value is None:
        return "(not set)"
    if value is True:
        return "on"
    if value is False:
        return "off"
    return str(value)
