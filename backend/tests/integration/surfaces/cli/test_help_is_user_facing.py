"""Every command's ``--help`` is written for the person running it.

A command docstring is also the maintainer's note on why the command is shaped
as it is — spec citations, ADR names, the helpers and routes it goes through.
Click prints a docstring only up to a ``\\f`` line, so those notes live after
one. This walks the whole command tree and fails on any help text that still
carries them where a user reads it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import typer

from coffer.surfaces.cli.main import app

_MAINTAINER_MARKERS = (
    'spec "',
    "ADR",
    "_client",
    "raise_for_status",
    ".py",
    "Requirement",
    "/api/v1",
    "GET /",
    "Settings → Engine",
)


def _walk(cmd: Any, path: tuple[str, ...]) -> Iterator[tuple[str, Any]]:
    yield " ".join(path), cmd
    for name, sub in getattr(cmd, "commands", {}).items():
        yield from _walk(sub, (*path, name))


_COMMANDS = list(_walk(typer.main.get_command(app), ("coffer",)))


def _user_facing_help(cmd: Any) -> str:
    """The text ``--help`` prints: the docstring up to ``\\f``, and every
    option's and argument's own help."""
    parts = [(cmd.help or "").partition("\f")[0]]
    parts += [p.help for p in cmd.params if getattr(p, "help", None)]
    return "\n".join(parts)


def test_the_walk_reaches_every_group_and_leaf() -> None:
    names = {name for name, _cmd in _COMMANDS}
    # A walk that stopped at the root would pass every check below vacuously.
    assert len(_COMMANDS) > 150
    assert {"coffer daemon status", "coffer sync remote pause", "coffer channel set"} <= names


@pytest.mark.parametrize(("name", "cmd"), _COMMANDS, ids=[name for name, _ in _COMMANDS])
def test_help_carries_no_maintainer_notes(name: str, cmd: Any) -> None:
    text = _user_facing_help(cmd)
    found = [marker for marker in _MAINTAINER_MARKERS if marker in text]
    assert not found, f"`{name} --help` shows maintainer notes {found}; move them after a \\f line"


@pytest.mark.parametrize(("name", "cmd"), _COMMANDS, ids=[name for name, _ in _COMMANDS])
def test_every_command_says_what_it_does(name: str, cmd: Any) -> None:
    assert (cmd.help or "").partition("\f")[0].strip(), f"`{name} --help` has no description"
