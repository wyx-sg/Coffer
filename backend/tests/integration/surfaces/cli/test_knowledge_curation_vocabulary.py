"""`coffer knowledge --help` calls curation Curate, never merge.

Spec knowledge "Present a collection as one tree in the web UI": the pass is
named Curate / Curation on every surface — the web UI (its half is
``frontend/src/i18n/curationVocabulary.test.ts``), the CLI help and the docs.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app as cli_app


def _command_paths(group: Any, prefix: list[str]) -> list[list[str]]:
    paths = [prefix]
    for name, command in group.commands.items():
        if hasattr(command, "commands"):
            paths += _command_paths(command, [*prefix, name])
        else:
            paths.append([*prefix, name])
    return paths


@pytest.mark.acceptance(spec="knowledge", scenario="curation is called curate, never merge")
def test_every_knowledge_help_line_says_curate_and_none_says_merge() -> None:
    knowledge = get_command(cli_app).commands["knowledge"]  # type: ignore[attr-defined]

    helps: dict[str, str] = {}
    for path in _command_paths(knowledge, ["knowledge"]):
        result = CliRunner().invoke(cli_app, [*path, "--help"])
        assert result.exit_code == 0, (path, result.output)
        helps[" ".join(path)] = result.output

    for name, text in helps.items():
        assert not re.search(r"\bmerg", text, re.IGNORECASE), name
    assert "curate" in helps["knowledge"].lower()
    assert "knowledge curate" in helps
