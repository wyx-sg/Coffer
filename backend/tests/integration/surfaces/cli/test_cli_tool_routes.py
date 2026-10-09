"""Command-line tools added by hand (spec skill-manager "Declare a
command-line tool without a skill"), over the real app with the probe faked at
the composition root."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest

from coffer.infrastructure.vault.home import vault_root
from tests.support.cli_requirements import FakeCommand, FakeCommandProbe

from ._cli_requirements_app import CliDaemon, boot_cli_daemon

_STATE = "state/cli-tools/tools.json"


@pytest.fixture
def probe() -> FakeCommandProbe:
    return FakeCommandProbe({"jq": FakeCommand("1.7.1"), "demo": FakeCommand("3.0.0")})


@pytest.fixture
def daemon(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, probe: FakeCommandProbe
) -> Iterator[CliDaemon]:
    yield from boot_cli_daemon(tmp_path, monkeypatch, probe=probe)


def _stored(tmp_path: pathlib.Path) -> dict[str, object]:
    return json.loads((vault_root(tmp_path) / _STATE).read_text(encoding="utf-8"))


@pytest.mark.acceptance(spec="skill-manager", scenario="a command-line tool is added with no skill")
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
    gone = daemon.client.delete("/clis/jq")
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "CLI_TOOL_NOT_DECLARED"
    unknown = daemon.client.patch("/clis/jq", json={"title": "x"})
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "CLI_NOT_KNOWN"


def test_changes_are_audited(daemon: CliDaemon) -> None:
    daemon.client.post("/clis", json={"command": "jq"})
    daemon.client.patch("/clis/jq", json={"title": "JSON"})
    daemon.client.delete("/clis/jq")
    events = daemon.client.get("/audit", params={"limit": 200}).json()
    kinds = [e["event_type"] for e in events["entries"]]
    for expected in ("cli_tool_added", "cli_tool_edited", "cli_tool_removed"):
        assert expected in kinds


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a hand-added tool and a skill are one entry"
)
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


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a path command's login check starts with its file name"
)
def test_a_path_commands_login_check_starts_with_its_file_name(daemon: CliDaemon) -> None:
    # A command given as a path is registered under its file name; the login
    # check starts with that name, and a refusal names the field and the name.
    daemon.probe.commands["tool"] = FakeCommand("1.0")  # type: ignore[attr-defined]
    refused = daemon.client.post(
        "/clis", json={"command": "/fake/bin/tool", "login_check": "/fake/bin/tool auth status"}
    )
    assert refused.status_code == 400, refused.text
    error = refused.json()["error"]
    assert error["code"] == "CLI_TOOL_INVALID"
    assert error["details"] == {
        "reason": "login_check_command",
        "field": "login_check",
        "command": "tool",
    }
    assert daemon.client.get("/clis").json()["items"] == []
    added = daemon.client.post(
        "/clis", json={"command": "/fake/bin/tool", "login_check": "tool auth status"}
    )
    assert added.status_code == 201, added.text
    assert added.json()["login"]["check"] == ["tool", "auth", "status"]


@pytest.mark.acceptance(spec="skill-manager", scenario="add, edit and remove a tool over REST")
def test_a_tool_is_added_edited_and_removed(daemon: CliDaemon) -> None:
    added = daemon.client.post("/clis", json={"command": "jq", "title": "JSON"})
    assert added.status_code == 201 and added.json()["added"] is True
    edited = daemon.client.patch("/clis/jq", json={"title": None})
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] != "JSON"
    assert daemon.client.delete("/clis/jq").status_code in (200, 204)
    assert daemon.client.get("/clis").json()["items"] == []
    again = daemon.client.delete("/clis/jq")
    assert again.status_code == 404
    assert again.json()["error"]["code"] == "CLI_TOOL_NOT_DECLARED"


@pytest.mark.acceptance(spec="skill-manager", scenario="a required tool takes the person's edits")
def test_a_required_tool_takes_the_persons_edits(daemon: CliDaemon, tmp_path: pathlib.Path) -> None:
    daemon.add_skill("data", '  - command: jq\n    title: From skill\n    min_version: "1.5"\n')
    r = daemon.client.patch("/clis/jq", json={"description": "Slice  JSON."})
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "Slice JSON." and r.json()["added"] is False
    stored = _stored(tmp_path)
    assert stored["tools"] == [] and stored["notes"] == {"jq": "Slice JSON."}
    r = daemon.client.patch(
        "/clis/jq",
        json={"title": "JSON", "min_version": "1.7", "login_check": "jq auth status"},
    )
    assert r.status_code == 200, r.text
    jq = r.json()
    assert jq["title"] == "JSON" and jq["min_version"] == "1.7" and jq["added"] is False
    assert jq["login"]["check"] == ["jq", "auth", "status"]
    assert jq["description"] == "Slice JSON." and len(jq["needed_by"]) == 1
    assert [e["command"] for e in _stored(tmp_path)["edits"]] == ["jq"]
    # null brings back what the skill says
    r = daemon.client.patch("/clis/jq", json={"title": None, "min_version": None})
    assert r.json()["title"] == "From skill" and r.json()["min_version"] == "1.5"
    bad = daemon.client.patch("/clis/jq", json={"login_check": "other status"})
    assert bad.status_code == 400
    unknown = daemon.client.patch("/clis/nope", json={"description": "x"})
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "CLI_NOT_KNOWN"
    daemon.client.patch("/clis/jq", json={"description": None, "login_check": None})
    assert not (vault_root(tmp_path) / _STATE).exists()
