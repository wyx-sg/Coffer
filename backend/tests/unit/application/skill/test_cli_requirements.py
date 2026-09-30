"""CliRequirementService over fake skills, a fake PATH and a fake Homebrew:
aggregation and order, the cache, the install refusals, the install job and
the attention items."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.skill.cli_attention import CliAttentionSource
from coffer.application.skill.cli_install import InstallState
from coffer.application.skill.cli_requirements import CliRequirementService, SkillDocument
from coffer.domain.audit import AuditEntry, AuditEventType
from coffer.domain.skill.cli_errors import (
    CliFormulaMismatch,
    CliInstallNotFound,
    CliNotInstallable,
    CliNotRequired,
    HomebrewNotFound,
)
from tests.support.cli_requirements import (
    FAKE_BREW,
    FakeCommand,
    FakeCommandProbe,
    FakeInstaller,
)


def _md(name: str, requires: str) -> str:
    return f"---\nname: {name}\ndescription: d\nrequires:\n{requires}---\n"


class _Skills:
    def __init__(self, docs: dict[str, str]) -> None:
        self.docs = docs

    async def skill_documents(self) -> Sequence[SkillDocument]:
        return [SkillDocument(uid=f"uid-{n}", name=n, text=t) for n, t in self.docs.items()]


class _AuditRepo:
    def __init__(self) -> None:
        self.rows: list[AuditEntry] = []

    async def insert(self, entry: AuditEntry) -> None:
        self.rows.append(entry)

    async def query(self, **_: Any) -> list[AuditEntry]:
        return list(self.rows)


def _service(
    docs: dict[str, str], probe: FakeCommandProbe, installer: FakeInstaller | None = None
) -> tuple[CliRequirementService, _AuditRepo]:
    repo = _AuditRepo()
    svc = CliRequirementService(
        skills=_Skills(docs),
        probe=probe,
        installer=installer or FakeInstaller(),
        audit=AuditService(repo),  # type: ignore[arg-type]
    )
    return svc, repo


_THREE = {
    "a-skill": _md("a-skill", '  - command: gh\n    min_version: "2.40"\n    brew: gh\n  - jq\n'),
    "b-skill": _md("b-skill", "  - uv\n  - command: jq\n    brew: jq\n"),
}


async def test_problems_first_then_by_name() -> None:
    probe = FakeCommandProbe({"gh": FakeCommand("2.30.0"), "uv": FakeCommand("0.4.18")})
    svc, _ = _service(_THREE, probe)
    listing = await svc.listing()
    assert [(v.required.command, v.status.value) for v in listing.items] == [
        ("jq", "missing"),
        ("gh", "outdated"),
        ("uv", "ready"),
    ]
    jq = listing.items[0]
    assert [n.skill_name for n in jq.required.needed_by] == ["a-skill", "b-skill"]
    assert jq.required.brew == "jq"  # a-skill declares jq without a formula


async def test_results_are_cached_until_checked_again() -> None:
    probe = FakeCommandProbe({"gh": FakeCommand("2.41")})
    svc, _ = _service({"s": _md("s", "  - gh\n")}, probe)
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
    svc, _ = _service({"s": doc}, probe)
    view = await svc.get("gh")
    assert view.status.value == "logged_out"
    assert probe.login_calls == [("/fake/bin/gh", "auth", "status")]


async def test_an_unknown_command_is_not_required() -> None:
    svc, _ = _service({}, FakeCommandProbe())
    with pytest.raises(CliNotRequired):
        await svc.get("gh")
    with pytest.raises(CliInstallNotFound):
        svc.install_status("gh")


async def test_install_refusals_run_nothing() -> None:
    installer = FakeInstaller()
    probe = FakeCommandProbe({"uv": FakeCommand("0.4")})
    svc, repo = _service(_THREE, probe, installer)
    with pytest.raises(CliFormulaMismatch):
        await svc.start_install("jq", "wget", actor="t")
    with pytest.raises(CliNotInstallable) as no_formula:
        await svc.start_install("uv", "uv", actor="t")
    assert no_formula.value.reason == "no_formula"
    installer.brew = None
    with pytest.raises(HomebrewNotFound):
        await svc.start_install("jq", "jq", actor="t")
    assert installer.runs == []
    assert repo.rows == []


async def test_a_present_current_command_is_not_installable() -> None:
    probe = FakeCommandProbe({"jq": FakeCommand("1.7")})
    svc, _ = _service({"s": _md("s", "  - command: jq\n    brew: jq\n")}, probe)
    with pytest.raises(CliNotInstallable) as refused:
        await svc.start_install("jq", "jq", actor="t")
    assert refused.value.reason == "not_needed"


async def test_install_then_upgrade_argv_audit_and_reprobe() -> None:
    probe = FakeCommandProbe({"gh": FakeCommand("2.30.0")})

    def _put_jq() -> None:
        probe.commands["jq"] = FakeCommand("1.7.1")

    installer = FakeInstaller(on_run=_put_jq)
    svc, repo = _service(_THREE, probe, installer)
    job = await svc.start_install("jq", "jq", actor="cli")
    assert job.argv == (FAKE_BREW, "install", "jq")
    await svc.wait_for_installs()
    done = svc.install_status("jq")
    assert done.state is InstallState.SUCCEEDED and done.exit_code == 0
    assert done.lines == installer.lines
    assert svc.install_status("jq", since=2).lines == ("==> Done",)
    assert (await svc.get("jq")).status.value == "ready"
    events = [(r.event_type, r.details) for r in repo.rows]
    assert events[0] == (
        AuditEventType.CLI_INSTALL_STARTED,
        {"command": "jq", "formula": "jq", "argv": [FAKE_BREW, "install", "jq"]},
    )
    assert events[1][0] == AuditEventType.CLI_INSTALL_FINISHED
    assert events[1][1]["exit_code"] == 0
    assert events[1][1]["output_tail"] == list(installer.lines)

    upgrade = await svc.start_install("gh", "gh", actor="cli")
    assert upgrade.argv == (FAKE_BREW, "upgrade", "gh")
    await svc.wait_for_installs()


async def test_a_failed_install_is_failed() -> None:
    installer = FakeInstaller(exit_code=1)
    svc, _ = _service(_THREE, FakeCommandProbe(), installer)
    await svc.start_install("jq", "jq", actor="t")
    await svc.wait_for_installs()
    job = svc.install_status("jq")
    assert job.state is InstallState.FAILED and job.exit_code == 1
    assert (await svc.get("jq")).status.value == "missing"


async def test_attention_items_one_per_problem() -> None:
    probe = FakeCommandProbe({"gh": FakeCommand("2.30.0"), "uv": FakeCommand("0.4.18")})
    svc, _ = _service(_THREE, probe)
    items = await CliAttentionSource(svc).items()
    assert [(i.kind, i.uid, i.reason_code) for i in items] == [
        ("cli", "jq", "cli_missing"),
        ("cli", "gh", "cli_outdated"),
    ]
    assert items[1].action.verb == "check"
    assert items[1].action.path == "/api/v1/clis/gh/check"
    assert items[1].severity.value == "warning"
