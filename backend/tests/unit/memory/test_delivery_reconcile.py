"""Unit tests for the delivery-hook reconcile target, driven through a real
``Reconciler`` over the dict-backed fakes of ``test_delivery_service``.

Covers the direction policy of ``DeliveryHookTarget`` (spec memory "Repair
stale delivery hooks", "Install delivery hooks explicitly and removably"). The
same policies on real files, and the dry-run and audit-failure
rules, are in ``tests/integration/application/test_delivery_hook_reconcile.py``.
"""

from __future__ import annotations

import json

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.delivery_reconcile import TARGET, DeliveryHookTarget
from coffer.application.reconcile.reconciler import Reconciler
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.delivery import DELIVERY_EVENTS, MARKER
from coffer.domain.reconcile import Disposition, Op, Outcome, PassReport, Trigger
from coffer.infrastructure.memory.delivery.codex import current_hash, trust_key
from tests.support.facets import TEST_COFFER_CLI, agent_catalog
from tests.unit.memory.test_delivery_service import (
    _CC_SETTINGS_PATH,
    _CC_UID,
    _CLAUDE_RESOURCE,
    _CODEX_HOOKS_PATH,
    _CODEX_RESOURCE,
    _CODEX_UID,
    FakeAgentLookup,
    FakeAuditRepo,
    FakeStore,
)

pytestmark = pytest.mark.asyncio

_STALE = f': {MARKER}; coffer memory context --agent cc --cwd "$PWD"'


class _Rig:
    def __init__(self, *, connected: list[str] | None = None) -> None:
        self.store = FakeStore()
        self.repo = FakeAuditRepo()
        audit = AuditService(self.repo)
        self.delivery = DeliveryService(
            agent_service=FakeAgentLookup([_CLAUDE_RESOURCE, _CODEX_RESOURCE]),
            audit=audit,
            store=self.store,
            catalog=agent_catalog(),
        )
        self.connected = list(connected or [])
        self.reconciler = Reconciler(audit=audit)

        async def _connected() -> list[str]:
            return list(self.connected)

        self.reconciler.register(DeliveryHookTarget(delivery=self.delivery, connected=_connected))

    async def installed(self, uid: str) -> bool:
        return (await self.delivery.status(uid)).installed

    async def command(self, uid: str) -> str:
        return (await self.delivery.status(uid)).command

    def age(self, uid: str = _CC_UID) -> None:
        """Rewrite an installed hook's command the way the CLI change aged it."""
        path = _CC_SETTINGS_PATH if uid == _CC_UID else _CODEX_HOOKS_PATH
        data = json.loads(self.store._files[path])
        for groups in data["hooks"].values():
            for group in groups:
                for leaf in group["hooks"]:
                    if MARKER in leaf["command"]:
                        leaf["command"] = _STALE
        self.store._files[path] = json.dumps(data)

    def events(self, event: AuditEventType) -> list:
        return [e for e in self.repo.entries if e.event_type == event.value]

    async def run(self, trigger: Trigger) -> PassReport:
        return await self.reconciler.run(targets=[TARGET], trigger=trigger)


def _only(report: PassReport):
    assert len(report.results) == 1, report.results
    return report.results[0]


# ---------------------------------------------------------------------------
# Repair stale delivery hooks
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="memory",
    scenario="a hook whose command went stale is repaired without being asked",
)
async def test_a_stale_command_is_rewritten_at_boot() -> None:
    """The one found in the field: ``--agent`` became ``--agent-uid`` and the
    stale entry still read as installed, because detection reads the marker."""
    rig = _Rig(connected=[_CC_UID])
    await rig.delivery.install(_CC_UID, actor="ui")
    rig.age()
    assert await rig.installed(_CC_UID)  # the entry that cannot work reads as installed

    result = _only(await rig.run(Trigger.BOOT))

    assert result.change.difference.op is Op.MODIFY
    assert result.change.difference.changed_params == ("command",)
    assert result.change.decision.reason_code == "stale_command"
    assert result.outcome is Outcome.APPLIED
    assert await rig.command(_CC_UID) == (
        f': {MARKER}; {TEST_COFFER_CLI} memory hook --agent-uid {_CC_UID} --cwd "$PWD"'
    )
    repairs = rig.events(AuditEventType.MEMORY_DELIVERY_INSTALLED)
    assert [e.actor for e in repairs] == ["ui", "system"]


async def test_an_older_builds_single_session_start_entry_gains_the_other_events() -> None:
    """A build before per-prompt delivery installed one ``SessionStart`` entry
    running ``memory context``; a period pass gives it all four events."""
    rig = _Rig(connected=[_CC_UID])
    old = f': {MARKER}; {TEST_COFFER_CLI} memory context --agent-uid {_CC_UID} --cwd "$PWD"'
    rig.store._files[_CC_SETTINGS_PATH] = json.dumps(
        {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": old}]}]}}
    )

    result = _only(await rig.run(Trigger.PERIOD))

    assert result.change.difference.op is Op.MODIFY
    assert result.change.difference.changed_params == ("command", "event")
    assert result.change.decision.reason_code == "stale_command"
    assert result.outcome is Outcome.APPLIED
    data = json.loads(rig.store._files[_CC_SETTINGS_PATH])
    assert set(data["hooks"]) == set(DELIVERY_EVENTS)
    command = await rig.command(_CC_UID)
    assert " memory hook " in command
    for event in DELIVERY_EVENTS:
        assert [g["hooks"][0]["command"] for g in data["hooks"][event]] == [command]


@pytest.mark.acceptance(
    spec="memory",
    scenario="a hook whose command went stale is repaired without being asked",
)
async def test_a_current_hook_is_left_alone_and_a_hookless_agent_is_given_none() -> None:
    """A no-op costs no write and no audit entry; and repair is not evangelism —
    a boot does not install a hook the user did not just ask for."""
    rig = _Rig(connected=[_CC_UID, _CODEX_UID])
    await rig.delivery.install(_CC_UID, actor="ui")
    writes = len(rig.store.writes)

    report = await rig.run(Trigger.BOOT)

    assert len(rig.store.writes) == writes
    (missing,) = report.results
    assert missing.change.difference.key == _CODEX_UID
    assert missing.change.difference.op is Op.ADD
    assert missing.change.decision.disposition is Disposition.REPORT
    assert missing.change.decision.reason_code == "hook_missing"
    assert missing.outcome is Outcome.PLANNED
    assert not await rig.installed(_CODEX_UID)
    assert _CODEX_HOOKS_PATH not in rig.store._files


async def test_a_missing_hook_is_reported_at_a_period_but_installed_on_a_manual_apply() -> None:
    rig = _Rig(connected=[_CC_UID])
    assert _only(await rig.run(Trigger.PERIOD)).outcome is Outcome.PLANNED
    assert not await rig.installed(_CC_UID)

    report = await rig.reconciler.apply([f"{TARGET}:{_CC_UID}"], actor="alice")

    assert _only(report).outcome is Outcome.APPLIED
    assert await rig.installed(_CC_UID)
    assert rig.events(AuditEventType.MEMORY_DELIVERY_INSTALLED)[-1].actor == "alice"


async def test_a_hook_on_an_agent_no_longer_connected_is_kept_and_kept_current() -> None:
    """Installing the hook was that user's explicit act; with memory on it
    stays, and a stale command in it is still repaired."""
    rig = _Rig(connected=[])
    await rig.delivery.install(_CC_UID, actor="ui")
    assert (await rig.run(Trigger.PERIOD)).results == ()
    assert await rig.installed(_CC_UID)

    rig.age()
    result = _only(await rig.run(Trigger.PERIOD))
    assert result.change.difference.op is Op.MODIFY
    assert result.change.decision.reason_code == "stale_command"
    assert await rig.command(_CC_UID) != _STALE


async def test_an_unreadable_settings_file_is_blocked_and_left_untouched() -> None:
    rig = _Rig(connected=[_CC_UID])
    rig.store._files[_CC_SETTINGS_PATH] = "{not valid json"

    result = _only(await rig.run(Trigger.MANUAL))

    assert result.change.decision.disposition is Disposition.BLOCKED
    assert result.change.decision.reason_code == "unreadable_config"
    assert str(_CC_SETTINGS_PATH) in result.change.decision.reason
    assert rig.store._files[_CC_SETTINGS_PATH] == "{not valid json"
    assert rig.store.writes == []


# ---------------------------------------------------------------------------
# A person asking installs a missing hook
# ---------------------------------------------------------------------------


async def test_a_manual_pass_installs_into_the_connected_agents_only() -> None:
    # "ghost" is connected but not registered: nothing to install it into.
    rig = _Rig(connected=[_CC_UID, "ghost"])

    result = _only(await rig.run(Trigger.MANUAL))

    assert result.change.decision.reason_code == "hook_missing"
    assert result.outcome is Outcome.APPLIED
    assert await rig.installed(_CC_UID)
    assert not await rig.installed(_CODEX_UID)
    (event,) = rig.events(AuditEventType.MEMORY_DELIVERY_INSTALLED)
    assert event.actor == "api"


async def test_a_manual_pass_leaves_an_installed_hook_alone() -> None:
    rig = _Rig(connected=[_CC_UID])
    await rig.delivery.install(_CC_UID, actor="ui")
    writes = len(rig.store.writes)

    assert (await rig.run(Trigger.MANUAL)).results == ()
    assert len(rig.store.writes) == writes


async def test_a_failed_audit_puts_back_what_the_repair_replaced() -> None:
    rig = _Rig(connected=[_CC_UID])
    await rig.delivery.install(_CC_UID, actor="ui")
    rig.age()
    before = rig.store._files[_CC_SETTINGS_PATH]

    async def _refuse(entry) -> None:
        raise RuntimeError("database is locked")

    rig.repo.insert = _refuse  # type: ignore[method-assign]
    result = _only(await rig.run(Trigger.PERIOD))

    assert result.outcome is Outcome.FAILED
    assert rig.store._files[_CC_SETTINGS_PATH] == before


async def test_a_failed_audit_removes_a_file_the_install_created() -> None:
    rig = _Rig(connected=[_CC_UID])

    async def _refuse(entry) -> None:
        raise RuntimeError("database is locked")

    rig.repo.insert = _refuse  # type: ignore[method-assign]
    result = _only(await rig.run(Trigger.MANUAL))

    assert result.outcome is Outcome.FAILED
    assert _CC_SETTINGS_PATH not in rig.store._files
    assert rig.store.deletes == [_CC_SETTINGS_PATH]


# ---------------------------------------------------------------------------
# Codex: the older build's hook, and trust
# ---------------------------------------------------------------------------

#: What a build before SessionStart support installed for Codex.
_LEGACY_CODEX = (
    f': {MARKER}; f="${{TMPDIR:-/tmp}}/.coffer-memory-fired-$PPID"; '
    f'[ -e "$f" ] || {{ : > "$f"; coffer memory context --agent-uid {_CODEX_UID} '
    '--cwd "$PWD"; }'
)
_CODEX_CONFIG_PATH = _CODEX_HOOKS_PATH.with_name("config.toml")


def _approve_codex(rig: _Rig) -> None:
    """What the user's approval in Codex's /hooks records."""
    text = rig.store._files[_CODEX_HOOKS_PATH]
    adapter = agent_catalog().delivery_hook(AgentType.CODEX)
    assert adapter is not None
    hooks = adapter.find_all(text)
    assert len(hooks) == len(DELIVERY_EVENTS)
    rig.store._files[_CODEX_CONFIG_PATH] = "".join(
        f'[hooks.state."{trust_key(str(_CODEX_HOOKS_PATH), hook)}"]\n'
        f'trusted_hash = "{current_hash(hook)}"\n'
        for hook in hooks
    )


@pytest.mark.acceptance(
    spec="memory", scenario="an older build's Codex hook is moved to SessionStart"
)
async def test_an_older_builds_codex_hook_is_moved_to_session_start_on_a_period() -> None:
    """The migration needs no person: the entry an older build left on
    UserPromptSubmit differs in event and command, so a period pass rewrites
    it — the foreign hook beside it stays."""
    rig = _Rig(connected=[_CODEX_UID])
    foreign = {"hooks": [{"type": "command", "command": "/skynet/beforeSubmitPrompt.sh"}]}
    legacy = {"hooks": [{"type": "command", "command": _LEGACY_CODEX, "timeout": 10}]}
    rig.store._files[_CODEX_HOOKS_PATH] = json.dumps(
        {"hooks": {"UserPromptSubmit": [foreign, legacy]}}
    )

    result = _only(await rig.run(Trigger.PERIOD))

    assert result.change.difference.op is Op.MODIFY
    assert result.change.difference.changed_params == ("command", "event", "trust")
    assert result.change.decision.reason_code == "stale_command"
    assert result.outcome is Outcome.APPLIED
    data = json.loads(rig.store._files[_CODEX_HOOKS_PATH])
    assert set(data["hooks"]) == set(DELIVERY_EVENTS)
    ups_foreign, ups_coffer = data["hooks"]["UserPromptSubmit"]
    assert ups_foreign == foreign
    assert _LEGACY_CODEX not in rig.store._files[_CODEX_HOOKS_PATH]
    command = await rig.command(_CODEX_UID)
    assert command.startswith(f": {MARKER}; {TEST_COFFER_CLI} ")
    assert ups_coffer["hooks"][0]["command"] == command
    for event in ("SessionStart", "PreToolUse", "PostToolUse"):
        (entry,) = data["hooks"][event]
        assert entry["hooks"][0]["command"] == command


@pytest.mark.acceptance(
    spec="memory", scenario="a current Codex hook Codex has not approved is reported, not written"
)
async def test_an_untrusted_codex_hook_is_reported_and_never_approved_by_coffer() -> None:
    rig = _Rig(connected=[_CODEX_UID])
    await rig.delivery.install(_CODEX_UID, actor="ui")
    writes = len(rig.store.writes)

    for trigger in (Trigger.PERIOD, Trigger.MANUAL):
        result = _only(await rig.run(trigger))
        assert result.change.difference.changed_params == ("trust",)
        assert result.change.decision.disposition is Disposition.REPORT
        assert result.change.decision.reason_code == "hook_untrusted"
        assert "/hooks" in result.change.decision.reason
        assert result.outcome is Outcome.PLANNED
    assert len(rig.store.writes) == writes
    assert _CODEX_CONFIG_PATH not in rig.store._files

    _approve_codex(rig)
    assert (await rig.run(Trigger.PERIOD)).results == ()
