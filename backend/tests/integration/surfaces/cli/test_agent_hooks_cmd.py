"""``coffer agent hooks`` against the real app (spec agent-registry "List
every hook in the agent's native config")."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.domain.memory.delivery import (
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_MATCHER,
    SESSION_START,
    SHELL_TOOL_MATCHER,
    USER_PROMPT_SUBMIT,
)
from coffer.surfaces.cli.main import app as cli_app

from ._real_app import boot, extract_json

_runner = CliRunner()

#: The events Coffer's hook sits on, as the listing spells them.
_EVENTS = "PostToolUse,PreToolUse,SessionStart,UserPromptSubmit"


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
    assert daemon.post("/agents", json={"type": "claude_code"}).status_code == 201

    plain = _runner.invoke(cli_app, ["agent", "hooks", "claude-code"], env={"COLUMNS": "250"})
    assert plain.exit_code == 0, plain.output
    assert "PreToolUse [Bash]  (user)  lint.sh" in plain.output
    assert f"coffer hook: missing on {_EVENTS}, last fired never" in plain.output

    as_json = _runner.invoke(cli_app, ["agent", "hooks", "claude-code", "--json"])
    assert as_json.exit_code == 0, as_json.output
    body = extract_json(as_json.output)
    assert [h["command"] for h in body["items"]] == ["lint.sh"]

    missing = _runner.invoke(cli_app, ["agent", "hooks", "nobody"])
    assert missing.exit_code != 0


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="report whether Codex trusts Coffer's hook"
)
def test_the_cli_says_when_codex_has_not_approved_coffers_hook(
    daemon: TestClient, tmp_path: pathlib.Path
) -> None:
    """An installed, current Codex hook that Codex will skip reads as such, with
    what the user does about it — Coffer never approves its own hook."""
    codex = tmp_path / ".codex"
    codex.mkdir()
    created = daemon.post("/agents", json={"type": "codex"})
    assert created.status_code == 201, created.text
    uid = created.json()["uid"]
    expected = daemon.get(f"/agents/{uid}/hooks").json()["coffer_hook"]["expected_command"]
    assert " memory hook " in expected
    assert expected.split()[2].startswith("/"), "the CLI is called by absolute path"

    def entry(matcher: str | None, timeout: int) -> dict[str, object]:
        group: dict[str, object] = {
            "hooks": [{"type": "command", "command": expected, "timeout": timeout}]
        }
        if matcher is not None:
            group["matcher"] = matcher
        return group

    hooks = {
        SESSION_START: [entry(SESSION_MATCHER, 10)],
        USER_PROMPT_SUBMIT: [entry(None, 5)],
        PRE_TOOL_USE: [entry(SHELL_TOOL_MATCHER, 5)],
        POST_TOOL_USE: [entry(SHELL_TOOL_MATCHER, 5)],
    }
    (codex / "hooks.json").write_text(json.dumps({"hooks": hooks}))

    plain = _runner.invoke(cli_app, ["agent", "hooks", "codex"], env={"COLUMNS": "250"})
    assert plain.exit_code == 0, plain.output
    assert f"coffer hook: current on {_EVENTS}, trust untrusted, last fired never" in (plain.output)
    assert "run /hooks there and trust it" in plain.output

    body = extract_json(_runner.invoke(cli_app, ["agent", "hooks", "codex", "--json"]).output)
    assert body["coffer_hook"]["trust"] == "untrusted"
    assert not (codex / "config.toml").exists()
