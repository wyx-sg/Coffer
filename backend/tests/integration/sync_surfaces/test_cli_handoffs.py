"""``coffer sync`` hand-offs: ``conflicts --prompt``, ``resolve --merged`` and
``status --prompt`` (spec vault-sync "Hand a conflict's merge to an agent",
"Hand a remote's failure to an agent")."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.sync_cmd import app

from .conftest import client_for
from .harness import Box

DOC = "knowledge/team/on-call.md"
runner = CliRunner()


def _cli(monkeypatch: pytest.MonkeyPatch, box: Box) -> None:
    client = client_for(box)
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, None))


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a conflict's merge is handed to an agent and recorded with I merged it",
)
def test_an_agent_merge_is_handed_off_and_recorded_from_the_command_line(
    monkeypatch: pytest.MonkeyPatch, pair: tuple[Box, Box]
) -> None:
    mac, mini = pair
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")
    _cli(monkeypatch, mini)
    assert "stopped" in runner.invoke(app, ["now"]).output
    listed = runner.invoke(app, ["conflicts"])
    assert "coffer sync conflicts --prompt" in listed.output
    prompt = runner.invoke(app, ["conflicts", "--prompt"])
    assert prompt.exit_code == 0 and "coffer sync resolve --merged" in prompt.output
    copy = Path(runner.invoke(app, ["edit", DOC]).output.strip())
    assert str(copy) in prompt.output
    refused = runner.invoke(app, ["resolve", "--merged"])
    assert refused.exit_code != 0, "a copy with markers left is refused"
    copy.write_text("Mac on Mondays, Mini on Fridays.\n")
    assert runner.invoke(app, ["resolve", DOC, "--merged"]).exit_code == 2
    merged = runner.invoke(app, ["resolve", "--merged"])
    assert merged.exit_code == 0 and "1 of 1 resolved" in merged.output
    assert runner.invoke(app, ["continue"]).exit_code == 0
    assert mini.disk(DOC) == b"Mac on Mondays, Mini on Fridays.\n"
    assert runner.invoke(app, ["conflicts", "--prompt"]).exit_code == 5


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a refused push carries a hand-off without a secret"
)
def test_status_prompt_prints_a_refused_push_hand_off(
    monkeypatch: pytest.MonkeyPatch, pair: tuple[Box, Box]
) -> None:
    mac, _mini = pair
    _cli(monkeypatch, mac)
    assert runner.invoke(app, ["status", "--prompt"]).exit_code == 5
    hook = Path(mac.url) / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'protected branch hook declined' >&2\nexit 1\n")
    hook.chmod(0o755)
    mac.put("knowledge/team/deploy.md", "Deploy.\n")
    runner.invoke(app, ["now"])
    shown = runner.invoke(app, ["status"])
    assert "coffer sync status --prompt" in shown.output
    prompt = runner.invoke(app, ["status", "--prompt"])
    assert prompt.exit_code == 0 and "refused this machine's push" in prompt.output
