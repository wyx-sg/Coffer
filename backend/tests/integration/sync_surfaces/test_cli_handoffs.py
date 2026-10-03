"""``coffer sync`` hand-offs: ``conflicts --prompt``, ``resolve --edited`` and
``status --prompt`` (spec vault-sync "Hand conflicting files to an agent",
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
    scenario="an agent's merge is shown to be checked and marked resolved",
)
def test_an_agent_merge_is_handed_off_and_resolved_from_the_command_line(
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
    assert prompt.exit_code == 0 and DOC in prompt.output
    assert "coffer sync" not in prompt.output and "git -C" not in prompt.output
    copy = Path(runner.invoke(app, ["edit", DOC]).output.strip())
    assert str(copy) in prompt.output
    assert "with an agent" in runner.invoke(app, ["conflicts"]).output
    refused = runner.invoke(app, ["resolve", DOC, "--edited"])
    assert refused.exit_code != 0, "a copy with markers left is refused"
    copy.write_text("Mac on Mondays, Mini on Fridays.\n")
    assert "merged by an agent" in runner.invoke(app, ["conflicts"]).output
    resolved = runner.invoke(app, ["resolve", DOC, "--edited"])
    assert resolved.exit_code == 0 and "1 of 1 resolved" in resolved.output
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
