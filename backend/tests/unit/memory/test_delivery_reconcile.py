"""Unit tests for the delivery-hook reconcile target, driven through a real
``Reconciler`` over the dict-backed fakes of ``test_delivery_service``.

Covers the direction policy of ``DeliveryHookTarget`` (spec memory "Repair
stale delivery hooks", "Install delivery hooks explicitly and removably"; spec
experimental-features "Withdraw what a switched-off feature put in front of
agents") and the ``memory`` switch subscriber that asks the reconciler for a
pass. The same policies on real files, and the dry-run and audit-failure
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

#: An installed hook whose CLI has since moved: marker intact, command stale.
_STALE = f': {MARKER}; /moved/away/coffer memory hook --agent-uid {_CC_UID} --cwd "$PWD"'


class _Features:
    def __init__(self, memory: bool) -> None:
        self.memory = memory

    def is_enabled(self, key: str) -> bool:
        assert key == "memory"
        return self.memory


class _Rig:
    def __init__(self, *, memory: bool = True, connected: list[str] | None = None) -> None:
        self.store = FakeStore()
        self.repo = FakeAuditRepo()
        audit = AuditService(self.repo)
        self.delivery = DeliveryService(
            agent_service=FakeAgentLookup([_CLAUDE_RESOURCE, _CODEX_RESOURCE]),
            audit=audit,
            store=self.store,
            catalog=agent_catalog(),
        )
        self.features = _Features(memory)
        self.connected = list(connected or [])
        self.reconciler = Reconciler(audit=audit)

        async def _connected() -> list[str]:
            return list(self.connected)

        self.reconciler.register(
            DeliveryHookTarget(delivery=self.delivery, features=self.features, connected=_connected)
        )

    async def installed(self, uid: str) -> bool:
        return (await self.delivery.status(uid)).installed

    async def command(self, uid: str) -> str:
        return (await self.delivery.status(uid)).command

    def age(self, uid: str = _CC_UID) -> None:
        """Rewrite an installed hook's command the way a moved CLI ages it."""
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
    """The stale entry still reads as installed, because detection reads the
    marker; the pass judges the whole command."""
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


async def test_a_hook_missing_some_events_gains_the_others() -> None:
    """The event set is judged too: a hook left on ``SessionStart`` alone
    (the other entries deleted by hand) gets all four events back on a period
    pass."""
    rig = _Rig(connected=[_CC_UID])
    current = f': {MARKER}; {TEST_COFFER_CLI} memory hook --agent-uid {_CC_UID} --cwd "$PWD"'
    rig.store._files[_CC_SETTINGS_PATH] = json.dumps(
        {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": current}]}]}}
    )

    result = _only(await rig.run(Trigger.PERIOD))

    assert result.change.difference.op is Op.MODIFY
    assert result.change.difference.changed_params == ("event",)
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

    result = _only(await rig.run(Trigger.SWITCH))

    assert result.change.decision.disposition is Disposition.BLOCKED
    assert result.change.decision.reason_code == "unreadable_config"
    assert str(_CC_SETTINGS_PATH) in result.change.decision.reason
    assert rig.store._files[_CC_SETTINGS_PATH] == "{not valid json"
    assert rig.store.writes == []


# ---------------------------------------------------------------------------
# The ``memory`` switch
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="switching memory on installs the memory hook again",
)
async def test_switching_on_installs_into_the_connected_agents_only() -> None:
    # "ghost" is connected but not registered: nothing to install it into.
    rig = _Rig(connected=[_CC_UID, "ghost"])

    result = _only(await rig.run(Trigger.SWITCH))

    assert result.change.decision.reason_code == "hook_missing"
    assert result.outcome is Outcome.APPLIED
    assert await rig.installed(_CC_UID)
    assert not await rig.installed(_CODEX_UID)
    (event,) = rig.events(AuditEventType.MEMORY_DELIVERY_INSTALLED)
    assert event.actor == "system:features"


async def test_switching_on_leaves_an_installed_hook_alone() -> None:
    rig = _Rig(connected=[_CC_UID])
    await rig.delivery.install(_CC_UID, actor="ui")
    writes = len(rig.store.writes)

    assert (await rig.run(Trigger.SWITCH)).results == ()
    assert len(rig.store.writes) == writes


async def test_a_manual_pass_installs_a_missing_hook_too() -> None:
    rig = _Rig(connected=[_CC_UID])

    result = _only(await rig.run(Trigger.MANUAL))

    assert result.outcome is Outcome.APPLIED
    assert await rig.installed(_CC_UID)


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="memory off withdraws the memory delivery hook",
)
async def test_switching_off_and_a_boot_with_memory_off_withdraw_everywhere() -> None:
    rig = _Rig(memory=False, connected=[_CC_UID])
    await rig.delivery.install(_CC_UID, actor="ui")
    await rig.delivery.install(_CODEX_UID, actor="ui")

    report = await rig.run(Trigger.SWITCH)

    assert {r.change.decision.reason_code for r in report.results} == {"feature_off"}
    assert all(r.outcome is Outcome.APPLIED for r in report.results)
    assert not await rig.installed(_CC_UID)
    assert not await rig.installed(_CODEX_UID)
    removed = rig.events(AuditEventType.MEMORY_DELIVERY_REMOVED)
    assert sorted(e.resource_name for e in removed) == ["cc", "codex"]
    assert {e.actor for e in removed} == {"system:features"}

    await rig.delivery.install(_CODEX_UID, actor="ui")
    assert _only(await rig.run(Trigger.BOOT)).outcome is Outcome.APPLIED
    assert not await rig.installed(_CODEX_UID)
    assert rig.events(AuditEventType.MEMORY_DELIVERY_REMOVED)[-1].actor == "system"


async def test_with_memory_off_nothing_is_desired_and_no_connection_is_asked() -> None:
    rig = _Rig(memory=False)

    async def _never() -> list[str]:
        raise AssertionError("with memory off nobody asks who is connected")

    target = DeliveryHookTarget(delivery=rig.delivery, features=rig.features, connected=_never)
    assert await target.desired() == []


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
    result = _only(await rig.run(Trigger.SWITCH))

    assert result.outcome is Outcome.FAILED
    assert _CC_SETTINGS_PATH not in rig.store._files
    assert rig.store.deletes == [_CC_SETTINGS_PATH]


# ---------------------------------------------------------------------------
# Codex: trust
# ---------------------------------------------------------------------------

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
