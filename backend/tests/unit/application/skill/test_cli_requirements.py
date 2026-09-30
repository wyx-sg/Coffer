"""CliRequirementService over fake skills and a fake PATH: aggregation and
order, the cache, the hand-off prompt per status and the attention items."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from coffer.application.skill.cli_attention import CliAttentionSource
from coffer.application.skill.cli_requirements import CliRequirementService, SkillDocument
from coffer.domain.skill.cli_errors import CliNotRequired
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
