"""``coffer sync ...`` against the in-process sync routes (spec vault-sync)."""

from __future__ import annotations

import json

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
    spec="vault-sync", scenario="the status command reports the remote's settings"
)
def test_status_now_and_history(monkeypatch: pytest.MonkeyPatch, pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    _cli(monkeypatch, mac)
    mac.put("knowledge/team/deploy.md", "Deploy.\n")
    shown = runner.invoke(app, ["status"])
    assert shown.exit_code == 0, shown.output
    assert "1 change(s) in 1 commit(s) waiting to push" in shown.output
    assert "2 knowledge documents" in shown.output
    ran = runner.invoke(app, ["now"])
    assert ran.exit_code == 0 and "pushed" in ran.output
    history = runner.invoke(app, ["history", "--limit", "3"])
    assert history.exit_code == 0 and "pushed" in history.output
    as_json = runner.invoke(app, ["status", "--json"])
    assert '"configured": true' in as_json.output


@pytest.mark.acceptance(
    spec="vault-sync", scenario="keeping this machine's version continues the round"
)
def test_a_stopped_round_is_resolved_from_the_command_line(
    monkeypatch: pytest.MonkeyPatch, pair: tuple[Box, Box]
) -> None:
    mac, mini = pair
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")
    _cli(monkeypatch, mini)

    assert "stopped" in runner.invoke(app, ["now"]).output
    status = runner.invoke(app, ["status"])
    assert status.exit_code == 1
    assert "file(s) to resolve" in status.output
    listed = runner.invoke(app, ["conflicts"])
    assert DOC in listed.output and "0 of 1 resolved" in listed.output
    edited = runner.invoke(app, ["edit", DOC])
    assert edited.exit_code == 0 and "sync-conflicts" in edited.output
    both = runner.invoke(app, ["resolve", DOC, "--mine", "--theirs"])
    assert both.exit_code == 2
    resolved = runner.invoke(app, ["resolve", DOC, "--theirs"])
    assert resolved.exit_code == 0 and "1 of 1 resolved" in resolved.output
    done = runner.invoke(app, ["continue"])
    assert done.exit_code == 0, done.output
    assert mini.disk(DOC) == b"Mac rotates on Mondays.\n"
    assert runner.invoke(app, ["conflicts"]).output.strip() == "no round is waiting for you"


@pytest.mark.acceptance(spec="vault-sync", scenario="a rollback shows its plan first")
def test_rollback_prints_the_plan_first(
    monkeypatch: pytest.MonkeyPatch, pair: tuple[Box, Box]
) -> None:
    mac, mini = pair
    mac.put(DOC, "Rotates on Tuesdays.\n")
    mac.round()
    pulled = mini.round()
    _cli(monkeypatch, mini)
    declined = runner.invoke(app, ["rollback", str(pulled.id)], input="n\n")
    assert declined.exit_code == 1
    assert f"modified {DOC}" in " ".join(declined.output.split())
    assert mini.disk(DOC) == b"Rotates on Tuesdays.\n"
    rolled = runner.invoke(app, ["rollback", str(pulled.id), "--yes"])
    assert rolled.exit_code == 0 and "rolled_back" in rolled.output
    assert mini.disk(DOC) == b"Primary on-call rotates every Monday.\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="pause and resume a remote from the command line"
)
def test_remote_machine_and_key_commands(
    monkeypatch: pytest.MonkeyPatch, pair: tuple[Box, Box]
) -> None:
    mac, _mini = pair
    _cli(monkeypatch, mac)
    check = runner.invoke(app, ["remote", "check"])
    assert check.exit_code == 0 and "a Coffer vault (layout 3)" in check.output
    paused = runner.invoke(app, ["remote", "pause"])
    assert paused.exit_code == 0 and "paused" in paused.output
    assert runner.invoke(app, ["status"]).exit_code == 0
    assert "enabled" in runner.invoke(app, ["remote", "resume"]).output
    assert runner.invoke(app, ["machine", "list"]).exit_code == 0
    machines = json.loads(runner.invoke(app, ["machine", "list", "--json"]).output)["machines"]
    assert [(m["name"], m["is_self"]) for m in machines] == [("Mac", True), ("Mini", False)]
    assert "renamed" in runner.invoke(app, ["machine", "rename", "Studio"]).output
    assert runner.invoke(app, ["machine", "rm", "mac"]).exit_code != 0
    assert "abc123abc123" in runner.invoke(app, ["key", "fingerprint"]).output
    cleared = runner.invoke(app, ["remote", "clear"])
    assert "cleared" in cleared.output


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a join states its case and its counts before applying"
)
def test_join_prints_the_preview_and_asks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object, pair: tuple[Box, Box]
) -> None:
    mac, _mini = pair
    _cli(monkeypatch, mac)
    declined = runner.invoke(app, ["join"], input="n\n")
    assert "joining as a" in declined.output and declined.exit_code == 1
    joined = runner.invoke(app, ["join", "--yes"])
    assert joined.exit_code == 0, joined.output


@pytest.mark.acceptance(
    spec="vault-sync", scenario="the command line checks a remote with the user name it is given"
)
def test_remote_check_sends_the_user_name(
    monkeypatch: pytest.MonkeyPatch, pair: tuple[Box, Box]
) -> None:
    mac, _mini = pair
    client = client_for(mac)
    sent: list[dict[str, object]] = []
    post = client.post

    def spy(path: str, **kwargs: object):  # type: ignore[no-untyped-def]
        if path == "/sync/remote/check":
            sent.append(kwargs["json"])  # type: ignore[arg-type]
        return post(path, **kwargs)

    monkeypatch.setattr(client, "post", spy)
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, None))

    given = runner.invoke(app, ["remote", "check", "--username", "oauth2"])
    assert given.exit_code == 0, given.output
    default = runner.invoke(app, ["remote", "check"])
    assert default.exit_code == 0, default.output
    assert [body["username"] for body in sent] == ["oauth2", "coffer"]
