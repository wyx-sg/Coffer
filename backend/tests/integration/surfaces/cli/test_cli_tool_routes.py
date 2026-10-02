"""Command-line tools added by hand, and the interface read from their help
(spec skill-manager "Declare a command-line tool without a skill", "Show a
command-line tool's full interface"), over the real app with the probe and the
help runner faked at the composition root."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest

from coffer.infrastructure.vault.home import vault_root
from tests.support.cli_requirements import DEMO_HELP, FakeCommand, FakeCommandProbe, FakeHelpRunner

from ._cli_requirements_app import CliDaemon, boot_cli_daemon

_STATE = "state/cli-tools/tools.json"


@pytest.fixture
def probe() -> FakeCommandProbe:
    return FakeCommandProbe({"jq": FakeCommand("1.7.1"), "demo": FakeCommand("3.0.0")})


@pytest.fixture
def daemon(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, probe: FakeCommandProbe
) -> Iterator[CliDaemon]:
    yield from boot_cli_daemon(
        tmp_path, monkeypatch, probe=probe, help_runner=FakeHelpRunner(dict(DEMO_HELP))
    )


def _stored(tmp_path: pathlib.Path) -> dict[str, object]:
    return json.loads((vault_root(tmp_path) / _STATE).read_text(encoding="utf-8"))


def test_a_tool_is_added_with_no_skill(daemon: CliDaemon, tmp_path: pathlib.Path) -> None:
    assert daemon.client.get("/clis").json()["items"] == []
    r = daemon.client.post(
        "/clis",
        json={
            "command": "jq",
            "title": "jq",
            "description": "Slice JSON.",
            "min_version": "1.6",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["command"] == "jq" and body["added"] is True and body["status"] == "ready"
    assert body["description"] == "Slice JSON." and body["min_version"] == "1.6"
    assert body["needed_by"] == [] and body["needed_by_servers"] == []
    listed = daemon.client.get("/clis").json()["items"]
    assert [i["command"] for i in listed] == ["jq"]
    # kept in the vault as a state document: declarations only, nothing found here
    stored = _stored(tmp_path)
    assert stored["tools"] == [
        {
            "command": "jq",
            "title": "jq",
            "description": "Slice JSON.",
            "min_version": "1.6",
            "login_check": None,
        }
    ]
    assert "path" not in json.dumps(stored)


def test_a_missing_tool_added_by_hand_raises_no_attention(daemon: CliDaemon) -> None:
    r = daemon.client.post("/clis", json={"command": "ghost", "min_version": "9.0"})
    assert r.status_code == 201 and r.json()["status"] == "missing"
    assert r.json()["handoff"] is not None  # the hand-off prompt still works
    attention = daemon.client.get("/attention").json()
    assert not [i for i in attention["items"] if i["kind"] == "cli"]


def test_adding_the_same_tool_twice_conflicts(daemon: CliDaemon) -> None:
    assert daemon.client.post("/clis", json={"command": "jq"}).status_code == 201
    again = daemon.client.post("/clis", json={"command": "jq"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CLI_TOOL_EXISTS"


@pytest.mark.parametrize(
    "body",
    [
        {"command": "rm -rf"},
        {"command": "../jq"},
        {"command": "jq", "min_version": "latest"},
        {"command": "jq", "login_check": "other auth status"},
        {"command": "jq", "title": "x" * 300},
        {"command": "/not/an/executable/file"},
    ],
)
def test_a_bad_declaration_is_refused(daemon: CliDaemon, body: dict[str, str]) -> None:
    r = daemon.client.post("/clis", json=body)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "CLI_TOOL_INVALID"
    assert daemon.client.get("/clis").json()["items"] == []


def test_preview_says_what_is_found_before_saving(daemon: CliDaemon) -> None:
    found = daemon.client.post("/clis/preview", json={"command": "jq"}).json()
    assert found == {
        "command": "jq",
        "path": "/fake/bin/jq",
        "version": "1.7.1",
        "added": False,
        "required": False,
    }
    gone = daemon.client.post("/clis/preview", json={"command": "ghost"}).json()
    assert gone["path"] is None and gone["version"] is None
    assert daemon.client.get("/clis").json()["items"] == []  # nothing saved


def test_a_tool_can_be_edited_and_removed(daemon: CliDaemon, tmp_path: pathlib.Path) -> None:
    daemon.client.post("/clis", json={"command": "jq", "title": "JSON", "min_version": "1.6"})
    r = daemon.client.patch("/clis/jq", json={"title": None, "login_check": "jq auth status"})
    assert r.status_code == 200, r.text
    edited = r.json()
    assert edited["title"] is None and edited["min_version"] == "1.6"
    assert edited["login"]["check"] == ["jq", "auth", "status"]
    bad = daemon.client.patch("/clis/jq", json={"min_version": "x"})
    assert bad.status_code == 400
    assert daemon.client.delete("/clis/jq").status_code == 204
    assert daemon.client.get("/clis").json()["items"] == []
    assert daemon.client.get("/clis/jq").status_code == 404
    assert not (vault_root(tmp_path) / _STATE).exists()
    for call in (
        daemon.client.patch("/clis/jq", json={"title": "x"}),
        daemon.client.delete("/clis/jq"),
    ):
        assert call.status_code == 404
        assert call.json()["error"]["code"] == "CLI_TOOL_NOT_DECLARED"


def test_changes_are_audited(daemon: CliDaemon) -> None:
    daemon.client.post("/clis", json={"command": "jq"})
    daemon.client.patch("/clis/jq", json={"title": "JSON"})
    daemon.client.delete("/clis/jq")
    events = daemon.client.get("/audit", params={"limit": 200}).json()
    kinds = [e["event_type"] for e in events["entries"]]
    for expected in ("cli_tool_added", "cli_tool_edited", "cli_tool_removed"):
        assert expected in kinds


def test_a_hand_added_tool_and_a_skill_are_one_entry(daemon: CliDaemon) -> None:
    uid = daemon.add_skill(
        "data", '  - command: jq\n    min_version: "1.5"\n    title: From skill\n'
    )
    daemon.client.post("/clis", json={"command": "jq", "title": "Mine", "min_version": "1.7"})
    items = daemon.client.get("/clis").json()["items"]
    assert len(items) == 1
    jq = items[0]
    assert jq["added"] is True and jq["title"] == "Mine" and jq["min_version"] == "1.7"
    assert [n["skill_uid"] for n in jq["needed_by"]] == [uid]
    # removing the declaration only drops the declaration
    assert daemon.client.delete("/clis/jq").status_code == 204
    left = daemon.client.get("/clis/jq").json()
    assert left["added"] is False and left["title"] == "From skill"
    assert left["min_version"] == "1.5" and len(left["needed_by"]) == 1


def test_an_absolute_path_names_the_command_and_stays_on_this_machine(
    daemon: CliDaemon, tmp_path: pathlib.Path
) -> None:
    daemon.probe.commands["tool"] = FakeCommand("1.0")  # type: ignore[attr-defined]
    r = daemon.client.post("/clis", json={"command": "/fake/bin/tool"})
    assert r.status_code == 201, r.text
    assert r.json()["command"] == "tool"
    assert "/fake/bin" not in json.dumps(_stored(tmp_path))
    local = (tmp_path / ".coffer" / "local" / "cli-paths.json").read_text(encoding="utf-8")
    assert json.loads(local) == {"tool": "/fake/bin/tool"}


def test_the_interface_is_read_on_request_and_kept(daemon: CliDaemon) -> None:
    daemon.client.post("/clis", json={"command": "demo"})
    before = daemon.client.get("/clis/demo/interface").json()
    assert before["status"] == "not_read" and before["nodes"] == []
    assert daemon.help_runner.calls == []  # a read of the page runs nothing
    read = daemon.client.post("/clis/demo/interface")
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["status"] == "ok" and not body["incomplete"]
    assert [n["path"] for n in body["nodes"]] == [[], ["init"], ["run"]]
    root = body["nodes"][0]
    assert root["usage"] == "demo [OPTIONS] COMMAND [ARGS]..."
    assert [s["name"] for s in root["subcommands"]] == ["init", "run"]
    assert root["options"][0] == {
        "names": ["-v", "--verbose"],
        "metavar": None,
        "description": "Be loud.",
        "default": None,
        "required": False,
    }
    assert "Usage: demo init" in body["nodes"][1]["raw"]
    calls = len(daemon.help_runner.calls)
    again = daemon.client.get("/clis/demo/interface").json()
    assert again["status"] == "ok" and len(again["nodes"]) == 3
    assert len(daemon.help_runner.calls) == calls  # served from what was kept


def test_a_changed_tool_reads_as_not_read_again(
    daemon: CliDaemon, probe: FakeCommandProbe, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon.client.post("/clis", json={"command": "demo"})
    daemon.client.post("/clis/demo/interface")
    assert daemon.client.get("/clis/demo/interface").json()["status"] == "ok"
    # a new build of the file: same path and version, different fingerprint
    monkeypatch.setattr(probe, "fingerprint", lambda _path: "rebuilt")
    assert daemon.client.get("/clis/demo/interface").json()["status"] == "not_read"
    # a new version is a new key too
    monkeypatch.undo()
    daemon.client.post("/clis/demo/interface")
    probe.commands["demo"].version = "4.0.0"
    daemon.client.post("/clis/demo/check")
    assert daemon.client.get("/clis/demo/interface").json()["status"] == "not_read"


def test_the_interface_of_a_missing_or_unknown_tool(daemon: CliDaemon) -> None:
    daemon.client.post("/clis", json={"command": "ghost"})
    gone = daemon.client.get("/clis/ghost/interface").json()
    assert gone["status"] == "unavailable" and "not found" in gone["message"]
    assert daemon.client.post("/clis/ghost/interface").json()["status"] == "unavailable"
    assert daemon.help_runner.calls == []
    assert daemon.client.get("/clis/nothing/interface").status_code == 404


def test_a_tool_with_no_help_says_so(daemon: CliDaemon, probe: FakeCommandProbe) -> None:
    daemon.help_runner.texts.clear()
    daemon.client.post("/clis", json={"command": "demo"})
    body = daemon.client.post("/clis/demo/interface").json()
    assert body["status"] == "no_help" and body["nodes"] == []
    assert "printed nothing" in body["message"]
