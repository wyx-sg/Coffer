"""Every drift remedy names an action that actually exists.

The remedy is the one line a person reads next to a drift row and then acts
on. It used to point at per-(skill, agent) re-enabling, which spec
skill-manager removed, and at a ``--force`` flag ``coffer skill verify`` never
had. These tests resolve every backticked ``coffer ...`` command in each remedy
against the real Typer tree, so a renamed or removed command fails here rather
than in front of a user.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import typer

from coffer.domain.skill.drift import DriftKind, suggested_remedy
from coffer.surfaces.cli.main import app

_COMMAND_RE = re.compile(r"`(coffer [^`]+)`")


def _root() -> Any:
    # Typer vendors its own click (``typer._click``), so groups are recognised
    # by their ``commands`` mapping rather than by ``isinstance(click.Group)``.
    return typer.main.get_command(app)


def _is_group(cmd: Any) -> bool:
    return isinstance(getattr(cmd, "commands", None), dict)


def _resolve(command_line: str) -> tuple[Any, list[str]]:
    """Walk ``coffer a b --flag <arg>`` down the click tree.

    Returns the leaf command and the option-looking tokens left over.
    """
    tokens = command_line.split()
    assert tokens[0] == "coffer"
    cmd = _root()
    rest = tokens[1:]
    while rest and _is_group(cmd) and not rest[0].startswith(("-", "<")):
        sub = cmd.commands.get(rest[0])
        assert sub is not None, f"{command_line!r}: no command {rest[0]!r} under {cmd.name!r}"
        cmd = sub
        rest = rest[1:]
    assert not _is_group(cmd), f"{command_line!r} names a group, not a command"
    return cmd, [t for t in rest if t.startswith("-")]


@pytest.mark.parametrize("kind", list(DriftKind))
def test_every_remedy_names_only_real_commands_and_flags(kind: DriftKind) -> None:
    remedy = suggested_remedy(kind)
    commands = _COMMAND_RE.findall(remedy)
    assert commands, f"{kind}: remedy names no concrete command: {remedy!r}"
    for line in commands:
        cmd, flags = _resolve(line)
        known = {opt for p in cmd.params for opt in getattr(p, "opts", [])}
        for flag in flags:
            assert flag in known, f"{kind}: {line!r} uses {flag!r}; {cmd.name} has {known}"


@pytest.mark.parametrize("kind", list(DriftKind))
def test_no_remedy_points_at_removed_operations(kind: DriftKind) -> None:
    remedy = suggested_remedy(kind).lower()
    assert "--force" not in remedy
    assert "re-enable" not in remedy
    assert "enable the skill" not in remedy


@pytest.mark.parametrize("kind", [DriftKind.MISSING_LINK, DriftKind.TAMPERED_LINK])
def test_repairable_kinds_point_at_verify_fix(kind: DriftKind) -> None:
    assert "`coffer skill verify --fix`" in suggested_remedy(kind)


def test_replaced_with_regular_says_the_person_moves_it_first() -> None:
    remedy = suggested_remedy(DriftKind.REPLACED_WITH_REGULAR)
    # Repair never touches foreign content (spec skill-manager "Repair
    # repairable drift from master"), so the person moves it themselves.
    assert "move it" in remedy.lower()
    assert remedy.index("move it") < remedy.index("`coffer skill verify --fix`")
