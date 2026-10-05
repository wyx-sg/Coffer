"""The required-command routes' ordering and hand-off prompt, over the real app with
the probe faked at the composition root (spec skill-manager "Serve required commands
on REST and the web")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest

from tests.support.cli_requirements import FakeCommand, FakeCommandProbe

from ._cli_requirements_app import CliDaemon, boot_cli_daemon


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[CliDaemon]:
    probe = FakeCommandProbe({"gh": FakeCommand("2.30.0"), "uv": FakeCommand("0.4.18")})
    for d in boot_cli_daemon(tmp_path, monkeypatch, probe=probe):
        d.add_skill("github", '  - command: gh\n    min_version: "2.40"\n')
        d.add_skill("data", "  - jq\n  - uv\n")
        yield d


@pytest.mark.acceptance(spec="skill-manager", scenario="required commands list problems first")
def test_the_list_puts_problems_first(daemon: CliDaemon) -> None:
    r = daemon.client.get("/clis")

    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [(i["command"], i["status"]) for i in items] == [
        ("jq", "missing"),
        ("gh", "outdated"),
        ("uv", "ready"),
    ]
    assert [n["skill_name"] for n in items[1]["needed_by"]] == ["github"]


@pytest.mark.acceptance(
    spec="skill-manager", scenario="the route and the page carry the same prompt"
)
def test_a_missing_command_carries_a_prompt_and_a_ready_one_none(daemon: CliDaemon) -> None:
    missing = daemon.client.get("/clis/jq")
    ready = daemon.client.get("/clis/uv")

    assert missing.status_code == 200 and ready.status_code == 200
    prompt = missing.json()["handoff"]["prompt"]
    assert "jq" in prompt
    # The list carries the same words the single read does, which is what the page copies.
    listed = {i["command"]: i for i in daemon.client.get("/clis").json()["items"]}
    assert listed["jq"]["handoff"]["prompt"] == prompt
    assert ready.json()["handoff"] is None


@pytest.mark.acceptance(spec="skill-manager", scenario="a profile's requires joins the skill's")
def test_a_profile_declared_command_names_its_profile_on_both_routes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for d in boot_cli_daemon(tmp_path, monkeypatch, probe=FakeCommandProbe({})):
        uid = d.add_skill(
            "logs",
            "  - gh\n",
            profiles={"acme-team": "---\nrequires:\n  commands: [smc]\n---\n# acme\n"},
        )
        items = {i["command"]: i for i in d.client.get("/clis").json()["items"]}
        assert items["gh"]["needed_by"][0]["profiles"] == []
        assert items["smc"]["needed_by"][0]["profiles"] == ["acme-team"]
        skill = d.client.get(f"/skills/{uid}").json()
        assert {r["command"]: r["profiles"] for r in skill["requires"]} == {
            "gh": [],
            "smc": ["acme-team"],
        }
