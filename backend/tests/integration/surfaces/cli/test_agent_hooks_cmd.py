"""``coffer agent hooks`` against the real app (spec agent-registry "List
every hook in the agent's native config")."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app as cli_app

from ._real_app import boot, extract_json

_runner = CliRunner()


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    claude = tmp_path / ".claude"
    claude.mkdir()
    settings = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "lint.sh"}]}
            ]
        }
    }
    (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    yield from boot(tmp_path, monkeypatch)


def test_the_cli_lists_hooks_and_coffers_health(daemon: TestClient) -> None:
    assert daemon.post("/agents", json={"type": "claude_code", "name": "cc"}).status_code == 201

    plain = _runner.invoke(cli_app, ["agent", "hooks", "cc"], env={"COLUMNS": "250"})
    assert plain.exit_code == 0, plain.output
    assert "PreToolUse [Bash]  (user)  lint.sh" in plain.output
    assert "coffer hook: missing on SessionStart, last fired never" in plain.output

    as_json = _runner.invoke(cli_app, ["agent", "hooks", "cc", "--json"])
    assert as_json.exit_code == 0, as_json.output
    body = extract_json(as_json.output)
    assert [h["command"] for h in body["items"]] == ["lint.sh"]

    missing = _runner.invoke(cli_app, ["agent", "hooks", "nobody"])
    assert missing.exit_code != 0
