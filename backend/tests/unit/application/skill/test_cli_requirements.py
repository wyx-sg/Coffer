"""CliRequirementService over fake skills and a fake PATH: aggregation and
order, the cache, the hand-off prompt per status and the attention items."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from coffer.application.skill.cli_attention import CliAttentionSource
from coffer.application.skill.cli_requirements import CliRequirementService, SkillDocument
from coffer.domain.skill.cli_errors import CliNotRequired
from coffer.domain.skill.cli_status import ServerLauncher, launcher_cli
from tests.support.cli_requirements import FAKE_MACHINE, FakeCommand, FakeCommandProbe


def _md(name: str, requires: str) -> str:
    return f"---\nname: {name}\ndescription: d\nrequires:\n{requires}---\n"


class _Skills:
    def __init__(self, docs: dict[str, str]) -> None:
        self.docs = docs

    async def skill_documents(self) -> Sequence[SkillDocument]:
        return [SkillDocument(uid=f"uid-{n}", name=n, text=t) for n, t in self.docs.items()]


def _service(docs: dict[str, str], probe: FakeCommandProbe) -> CliRequirementService:
    return CliRequirementService(skills=_Skills(docs), probe=probe, machine=lambda: FAKE_MACHINE)


_THREE = {
    "a-skill": _md("a-skill", '  - command: gh\n    min_version: "2.40"\n  - jq\n'),
    "b-skill": _md("b-skill", "  - uv\n  - jq\n"),
}


async def test_problems_first_then_by_name() -> None:
    probe = FakeCommandProbe({"gh": FakeCommand("2.30.0"), "uv": FakeCommand("0.4.18")})
    listing = await _service(_THREE, probe).listing()
    assert [(v.required.command, v.status.value) for v in listing.items] == [
        ("jq", "missing"),
        ("gh", "outdated"),
        ("uv", "ready"),
    ]
    jq = listing.items[0]
    assert [n.skill_name for n in jq.required.needed_by] == ["a-skill", "b-skill"]


async def test_results_are_cached_until_checked_again() -> None:
    probe = FakeCommandProbe({"gh": FakeCommand("2.41")})
    svc = _service({"s": _md("s", "  - gh\n")}, probe)
    await svc.listing()
    await svc.listing()
    await svc.get("gh")
    assert probe.located == ["gh"]
    await svc.check("gh")
    await svc.check_all()
    assert probe.located == ["gh", "gh", "gh"]


async def test_login_check_runs_the_located_file_and_logged_out_is_reported() -> None:
    probe = FakeCommandProbe({"gh": FakeCommand("2.41", logged_in=False, printed="octocat")})
    doc = _md("s", "  - command: gh\n    login_check: gh auth status\n")
    view = await _service({"s": doc}, probe).get("gh")
    assert view.status.value == "logged_out"
    assert probe.login_calls == [("/fake/bin/gh", "auth", "status")]
    assert view.handoff is not None and "octocat" not in view.handoff


async def test_an_unknown_command_is_not_required() -> None:
    with pytest.raises(CliNotRequired):
        await _service({}, FakeCommandProbe()).get("gh")


async def test_every_problem_carries_a_prompt_and_ready_carries_none() -> None:
    probe = FakeCommandProbe({"gh": FakeCommand("2.30.0"), "uv": FakeCommand("0.4.18")})
    views = {v.required.command: v for v in (await _service(_THREE, probe).listing()).items}
    jq, gh, uv = views["jq"].handoff, views["gh"].handoff, views["uv"].handoff
    assert jq is not None and jq.startswith("Please install the command-line tool `jq`")
    assert "- Needed by the Coffer skills: a-skill, b-skill." in jq
    assert f"- This machine: {FAKE_MACHINE}." in jq
    assert "run `jq --version`" in jq
    assert gh is not None and gh.startswith("Please update the command-line tool `gh`")
    assert "a-skill (version 2.40 or newer)" in gh
    assert uv is None


async def test_attention_items_one_per_problem() -> None:
    probe = FakeCommandProbe({"gh": FakeCommand("2.30.0"), "uv": FakeCommand("0.4.18")})
    items = await CliAttentionSource(_service(_THREE, probe)).items()
    assert [(i.kind, i.uid, i.reason_code) for i in items] == [
        ("cli", "jq", "cli_missing"),
        ("cli", "gh", "cli_outdated"),
    ]
    assert items[1].action.verb == "check"
    assert items[1].action.path == "/api/v1/clis/gh/check"
    assert items[1].severity.value == "warning"


class _Servers:
    def __init__(self, *launchers: tuple[str, str]) -> None:
        self.launchers = [ServerLauncher(f"uid-{name}", name, cmd) for name, cmd in launchers]

    async def stdio_launchers(self) -> Sequence[ServerLauncher]:
        return self.launchers


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="a stdio MCP server's launcher is listed under the command that provides it",
)
async def test_mcp_launchers_are_required_by_their_servers() -> None:
    probe = FakeCommandProbe({"node": FakeCommand("22.1.0")})
    profiling = _md("data-profiling", '  - command: uv\n    min_version: "0.4"\n')
    svc = CliRequirementService(
        skills=_Skills({"data-profiling": profiling}),
        probe=probe,
        machine=lambda: FAKE_MACHINE,
        servers=_Servers(("duckdb", "uvx"), ("files", "npx"), ("local", "./run.sh")),
    )
    views = {v.required.command: v for v in (await svc.listing()).items}
    assert sorted(views) == ["node", "uv"]
    uv = views["uv"]
    assert [n.skill_name for n in uv.required.needed_by] == ["data-profiling"]
    assert [(s.server_name, s.launcher) for s in uv.required.needed_by_servers] == [
        ("duckdb", "uvx")
    ]
    assert uv.status.value == "missing" and uv.handoff is not None
    assert "- Needed by the MCP servers Coffer starts: duckdb (started with `uvx`)." in uv.handoff
    assert "- Needed by the Coffer skills: data-profiling (version 0.4 or newer)." in uv.handoff
    node = views["node"]
    assert node.required.needed_by == () and node.status.value == "ready"
    assert (await svc.get("node")).required.needed_by_servers[0].server_name == "files"


async def test_a_launcher_only_servers_need_raises_no_cli_attention_item() -> None:
    svc = CliRequirementService(
        skills=_Skills({}),
        probe=FakeCommandProbe(),
        machine=lambda: FAKE_MACHINE,
        servers=_Servers(("duckdb", "uvx")),
    )
    listing = await svc.listing()
    assert [v.status.value for v in listing.items] == ["missing"]
    assert await CliAttentionSource(svc).items() == []


def _secret_md(name: str, secrets: str) -> str:
    return f"---\nname: {name}\ndescription: d\nrequires:\n  secrets: [{secrets}]\n---\n"


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="a secret a skill requires that is not set raises a needs-you item",
)
async def test_a_skill_missing_a_secret_raises_one_item_opening_secrets() -> None:
    stored = {"NPM_TOKEN"}
    asked: list[str] = []

    def secret_set(name: str) -> bool:
        asked.append(name)
        return name in stored

    svc = CliRequirementService(
        skills=_Skills(
            {
                "triage": _secret_md("triage", "GH_TOKEN, NPM_TOKEN, SLACK_TOKEN"),
                "publish": _secret_md("publish", "NPM_TOKEN"),
            }
        ),
        probe=FakeCommandProbe(),
        machine=lambda: FAKE_MACHINE,
        secret_set=secret_set,
    )
    missing = await svc.missing_secrets()
    assert [(m.skill_name, m.secret) for m in missing] == [
        ("triage", "GH_TOKEN"),
        ("triage", "SLACK_TOKEN"),
    ]
    [item] = await CliAttentionSource(svc).items()
    assert (item.kind, item.uid, item.title, item.reason_code) == (
        "skill",
        "uid-triage",
        "triage",
        "skill_missing_secret",
    )
    assert item.reason == (
        "secret GH_TOKEN is not set; secret SLACK_TOKEN is not set; the skill requires them."
    )
    assert (item.action.verb, item.action.method, item.action.path) == (
        "set_secret",
        "POST",
        "/api/v1/secrets",
    )
    assert item.action.body == {"ref": "secret/GH_TOKEN"}
    # A person's task: no hand-off prompt.
    assert item.handoff is None
    assert set(asked) == {"GH_TOKEN", "NPM_TOKEN", "SLACK_TOKEN"}


async def test_a_secret_once_set_clears_its_item() -> None:
    stored: set[str] = set()
    svc = CliRequirementService(
        skills=_Skills({"s": _secret_md("s", "API_KEY")}),
        probe=FakeCommandProbe(),
        machine=lambda: FAKE_MACHINE,
        secret_set=stored.__contains__,
    )
    [item] = await CliAttentionSource(svc).items()
    assert item.reason == "secret API_KEY is not set; the skill requires it."
    stored.add("API_KEY")
    assert await CliAttentionSource(svc).items() == []


async def test_without_a_secret_store_no_secret_is_reported() -> None:
    svc = _service({"s": _secret_md("s", "API_KEY")}, FakeCommandProbe())
    assert await svc.missing_secrets() == ()


def test_launcher_cli_maps_provided_launchers_and_skips_paths() -> None:
    assert [launcher_cli(c) for c in ("uvx", "npx", "bunx", "docker", "./run.sh", "/opt/x")] == [
        "uv",
        "node",
        "bun",
        "docker",
        None,
        None,
    ]
