"""`coffer sync file-answer` documents exactly the answers the route accepts
(spec vault-sync "Answer each conflicting file and continue the round")."""

from __future__ import annotations

import re

from typer.testing import CliRunner

from coffer.surfaces.cli.main import app
from coffer.surfaces.http.sync_stop_schemas import FileAnswerIn


def test_the_documented_answers_are_exactly_the_accepted_ones() -> None:
    schema = FileAnswerIn.model_json_schema()
    accepted = set(schema["$defs"]["Answer"]["enum"])
    result = CliRunner().invoke(app, ["sync", "file-answer", "--help"])
    assert result.exit_code == 0, result.output
    text = " ".join(result.output.replace("│", " ").split())
    found = re.search(r"answer \(([^)]*)\)", text)
    assert found, text
    documented = {a.strip() for a in found.group(1).split("|")}
    assert documented == accepted == {"mine", "theirs", "edited"}
