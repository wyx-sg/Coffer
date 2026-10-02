"""``coffer agent`` names the same argument the same way in every subcommand.

An existing agent is ``NAME`` (its name or uid) wherever it appears; the
commands that name an agent *type* (``add``, ``prompt``, ``models``) say
``TYPE``. No subcommand calls either one ``AGENT`` or ``AGENT_KEY``.
"""

from __future__ import annotations

from typing import Any

import typer.main

from coffer.surfaces.cli.main import app

_TYPE_COMMANDS = {"add", "prompt", "models"}


def _agent_group() -> Any:
    return typer.main.get_command(app).commands["agent"]  # type: ignore[attr-defined]


def _walk(group: Any, path: tuple[str, ...] = ()) -> Any:
    for name, cmd in group.commands.items():
        if hasattr(cmd, "commands"):
            yield from _walk(cmd, (*path, name))
        else:
            yield (*path, name), cmd


def _agent_argument(cmd: Any) -> str | None:
    """The metavar of the command's first positional argument, if it has one."""
    for param in cmd.params:
        if param.param_type_name == "argument":
            return str(param.metavar or param.name).upper()
    return None


def test_every_subcommand_names_its_agent_argument_the_same_way() -> None:
    seen: dict[tuple[str, ...], str] = {}
    for path, cmd in _walk(_agent_group()):
        metavar = _agent_argument(cmd)
        if metavar is not None:
            seen[path] = metavar

    assert seen, "the agent group exposes no subcommand with an argument"
    for path, metavar in seen.items():
        expected = "TYPE" if path[-1] in _TYPE_COMMANDS else "NAME"
        assert metavar == expected, f"coffer agent {' '.join(path)}: {metavar}, expected {expected}"
