"""The shape of a ``coffer config`` key, and the plumbing every key shares.

A key names its type, its help, the place that stores it, how to read it, how
to write it and — when it has a default — how to return to it (spec
resource-framework "Change every setting through one key-value command"). The
keys themselves live in ``_config_keys`` and ``_config_engine``; this module is
what they are made of.

A key never talks to the daemon unless it is read or written: ``daemon.port``
must work with no daemon running, so the client is opened lazily, once, by the
first key that needs it.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from coffer.surfaces.cli import _client as _cli_client


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
    #: The accepted values, as a person reads them ("on|off", "days|forever").
    type: str
    help: str
    #: Where the setting is kept: the REST route, or the pre-bind file.
    store: str
    parse: Callable[[str], Any]
    read: Callable[[Session], Reading]
    write: Callable[[Session, Any], list[str]]
    #: ``None`` for a key with no default, which refuses ``unset``.
    unset: Callable[[Session], list[str]] | None = None
    #: What to tell someone who tried to unset a key with no default.
    unset_hint: str = ""


@dataclass(frozen=True)
class Family:
    """Keys whose members only the daemon knows (``feature.<key>``,
    ``retention.<table>``)."""

    prefix: str
    members: Callable[[Session], list[Setting]]


class Session:
    """One command's lazily opened daemon client, with its GETs cached so a
    ``config list`` reads each settings document once."""

    def __init__(self, *, verbose: bool) -> None:
        self.verbose = verbose
        self._client: httpx.Client | None = None
        self._stack = contextlib.ExitStack()
        self._cache: dict[str, Any] = {}

    def client(self) -> httpx.Client:
        if self._client is None:
            c, _info = _cli_client.client_or_exit()
            self._client = self._stack.enter_context(c)
        return self._client

    def get(self, path: str) -> Any:
        if path not in self._cache:
            r = self.client().get(path)
            _cli_client.check(r, verbose=self.verbose)
            self._cache[path] = r.json()
        return self._cache[path]

    def send(self, method: str, path: str, body: Any = None) -> Any:
        r = self.client().request(method, path, json=body)
        _cli_client.check(r, verbose=self.verbose)
        self._cache.clear()
        return r.json() if r.content else None

    def close(self) -> None:
        self._stack.close()


def show(value: Any) -> str:
    """A JSON value as a person reads it."""
    if value is None:
        return "(not set)"
    if value is True:
        return "on"
    if value is False:
        return "off"
    return str(value)


# --- parsers: each names what it expected -----------------------------------


def _refuse(key: str, expected: str, raw: str) -> SettingValueError:
    return SettingValueError(f"{key} takes {expected}, got {raw!r}")


def switch(key: str) -> Callable[[str], bool]:
    def parse(raw: str) -> bool:
        if raw.lower() in ("on", "off"):
            return raw.lower() == "on"
        raise _refuse(key, "on or off", raw)

    return parse


def whole(
    key: str, expected: str, *, low: int = 1, high: int | None = None
) -> Callable[[str], int]:
    def parse(raw: str) -> int:
        try:
            n = int(raw)
        except ValueError:
            raise _refuse(key, expected, raw) from None
        if n < low or (high is not None and n > high):
            raise _refuse(key, expected, raw)
        return n

    return parse


def choice(key: str, options: tuple[str, ...]) -> Callable[[str], str]:
    def parse(raw: str) -> str:
        if raw in options:
            return raw
        raise _refuse(key, "one of " + ", ".join(options), raw)

    return parse


def text(key: str, expected: str) -> Callable[[str], str]:
    def parse(raw: str) -> str:
        if raw.strip():
            return raw.strip()
        raise _refuse(key, expected, raw)

    return parse


def days_or_forever(key: str) -> Callable[[str], int | None]:
    """A whole number of days (1-3650, the route's range), or ``forever``."""
    days = whole(key, "a whole number of days (1-3650) or 'forever'", high=3650)

    def parse(raw: str) -> int | None:
        return None if raw == "forever" else days(raw)

    return parse
