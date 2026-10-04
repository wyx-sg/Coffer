"""Every command on the command line has a recorded reason (spec
resource-framework "Keep the command line to what needs it")."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from coffer.surfaces.cli.command_reasons import COMMAND_REASONS, Reason
from coffer.surfaces.cli.main import app

_HIDDEN = {"memory hook", "proxy token"}


def _walk(cmd: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Every command in the tree, groups included; a group has ``.commands``."""
    yield path, cmd
    for name, sub in (getattr(cmd, "commands", None) or {}).items():
        yield from _walk(sub, (*path, name))


def _leaves() -> dict[str, Any]:
    root = typer.main.get_command(app)
    return {" ".join(p): c for p, c in _walk(root) if p and not getattr(c, "commands", None)}


def _groups() -> list[tuple[str, ...]]:
    root = typer.main.get_command(app)
    return [p for p, c in _walk(root) if getattr(c, "commands", None)]


@pytest.mark.acceptance(spec="resource-framework", scenario="every command has a recorded reason")
def test_every_command_has_a_recorded_reason() -> None:
    assert set(_leaves()) == set(COMMAND_REASONS)
    for path, (reason, why) in COMMAND_REASONS.items():
        assert isinstance(reason, Reason), path
        assert why.strip(), path
    assert {p for p, c in _leaves().items() if c.hidden} == _HIDDEN
    assert {COMMAND_REASONS[p][0] for p in _HIDDEN} == {Reason.PROGRAM}


def _unrecorded(leaves: set[str], recorded: set[str]) -> set[str]:
    """The commands the list does not know, and the list's rows with no command."""
    return leaves ^ recorded


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a command missing from the list fails the test"
)
def test_a_command_missing_from_the_list_fails_the_test() -> None:
    leaves, recorded = set(_leaves()), set(COMMAND_REASONS)
    assert _unrecorded(leaves, recorded) == set()
    # A command added without a row, and a row left behind by a removed command,
    # are each found: the comparison goes both ways.
    assert _unrecorded(leaves | {"sync now"}, recorded) == {"sync now"}
    assert _unrecorded(leaves, recorded | {"agent list"}) == {"agent list"}


def test_every_group_renders_its_help() -> None:
    runner = CliRunner()
    for path in _groups():
        result = runner.invoke(app, [*path, "--help"])
        assert result.exit_code == 0, (path, result.output)
