"""FeatureService: pin → setting → channel default, and what a switch does."""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.features import FeatureService, FeatureState
from coffer.application.memory.delivery_switch import memory_switch_subscriber
from coffer.domain.features import FeaturePinned, FeatureUnknown


class _FakeSettings:
    """An in-memory FeatureSettingsPort."""

    def __init__(self, stored: dict[str, bool] | None = None, *, fail: bool = False) -> None:
        self.stored = dict(stored or {})
        self.fail = fail
        self.writes: list[tuple[str, bool]] = []

    def read(self) -> dict[str, bool]:
        return dict(self.stored)

    def write(self, key: str, enabled: bool) -> None:
        if self.fail:
            raise OSError("disk full")
        self.writes.append((key, enabled))
        self.stored[key] = enabled


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a stable build starts with every experimental feature off",
)
def test_a_stable_build_with_nothing_set_has_every_feature_off() -> None:
    svc = FeatureService(channel="stable", settings=_FakeSettings())
    assert svc.list() == [
        FeatureState("vault_sync", False, "channel"),
        FeatureState("knowledge", False, "channel"),
        FeatureState("memory", False, "channel"),
    ]


def test_a_dev_build_with_nothing_set_has_every_feature_on() -> None:
    svc = FeatureService(channel="dev", settings=_FakeSettings())
    assert svc.enabled_map() == {"vault_sync": True, "knowledge": True, "memory": True}
    assert {s.source for s in svc.list()} == {"channel"}


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a machine setting overrides the channel default",
)
def test_a_machine_setting_overrides_the_channel_default() -> None:
    svc = FeatureService(channel="stable", settings=_FakeSettings({"memory": True}))
    assert svc.state("memory") == FeatureState("memory", True, "setting")
    assert svc.state("knowledge") == FeatureState("knowledge", False, "channel")
    assert svc.state("vault_sync") == FeatureState("vault_sync", False, "channel")


def test_a_pin_overrides_the_setting() -> None:
    svc = FeatureService(
        channel="dev",
        settings=_FakeSettings({"knowledge": True}),
        pins={"knowledge": False},
    )
    assert svc.state("knowledge") == FeatureState("knowledge", False, "pin")
    assert svc.is_enabled("knowledge") is False


def test_unregistered_keys_in_settings_and_pins_are_ignored() -> None:
    svc = FeatureService(
        channel="stable",
        settings=_FakeSettings({"workflow": True}),
        pins={"telemetry": True},
    )
    assert [s.key for s in svc.list()] == ["vault_sync", "knowledge", "memory"]
    with pytest.raises(FeatureUnknown):
        svc.is_enabled("workflow")


async def test_a_pinned_feature_cannot_be_switched_and_nothing_is_written() -> None:
    settings = _FakeSettings()
    svc = FeatureService(channel="dev", settings=settings, pins={"knowledge": False})
    with pytest.raises(FeaturePinned):
        await svc.set("knowledge", True)
    assert settings.writes == []
    assert svc.is_enabled("knowledge") is False


async def test_set_writes_the_setting_and_changes_the_state() -> None:
    settings = _FakeSettings()
    svc = FeatureService(channel="stable", settings=settings)
    after = await svc.set("vault_sync", True)
    assert after == FeatureState("vault_sync", True, "setting")
    assert settings.writes == [("vault_sync", True)]
    assert svc.is_enabled("vault_sync") is True


async def test_a_failed_write_leaves_the_state_as_it_was() -> None:
    svc = FeatureService(channel="stable", settings=_FakeSettings(fail=True))
    with pytest.raises(OSError):
        await svc.set("memory", True)
    assert svc.state("memory") == FeatureState("memory", False, "channel")


async def test_set_refuses_an_unknown_key() -> None:
    settings = _FakeSettings()
    svc = FeatureService(channel="dev", settings=settings)
    with pytest.raises(FeatureUnknown):
        await svc.set("workflow", True)
    assert settings.writes == []


async def test_subscribers_hear_a_change_sync_and_async() -> None:
    svc = FeatureService(channel="dev", settings=_FakeSettings())
    heard_sync: list[tuple[str, bool]] = []
    heard_async: list[tuple[str, bool]] = []

    def on_sync(key: str, enabled: bool) -> None:
        heard_sync.append((key, enabled))

    async def on_async(key: str, enabled: bool) -> None:
        heard_async.append((key, enabled))

    svc.subscribe(on_sync)
    svc.subscribe(on_async)
    await svc.set("memory", False)
    assert heard_sync == [("memory", False)]
    assert heard_async == [("memory", False)]


async def test_subscribers_hear_nothing_when_the_state_does_not_move() -> None:
    """On `dev`, writing `on` over the `on` default records a setting but is no change."""
    settings = _FakeSettings()
    svc = FeatureService(channel="dev", settings=settings)
    heard: list[tuple[str, bool]] = []
    svc.subscribe(lambda k, e: heard.append((k, e)))
    after = await svc.set("knowledge", True)
    assert after.source == "setting"
    assert settings.writes == [("knowledge", True)]
    assert heard == []


async def test_a_failing_subscriber_does_not_stop_the_others() -> None:
    svc = FeatureService(channel="dev", settings=_FakeSettings())
    heard: list[str] = []

    def broken(key: str, enabled: bool) -> None:
        raise RuntimeError("boom")

    svc.subscribe(broken)
    svc.subscribe(lambda k, e: heard.append(k))
    after = await svc.set("vault_sync", False)
    assert after.enabled is False
    assert heard == ["vault_sync"]


def test_the_channel_is_reported() -> None:
    assert FeatureService(channel="stable", settings=_FakeSettings()).channel == "stable"


class _Hooks:
    """Stands in for every agent's delivery hook: the reconcile yields to the
    loop part-way through, the way a real one waits on files, so two runs left
    to overlap would interleave."""

    def __init__(self) -> None:
        self.installed = True
        self.running = 0
        self.overlapped = False

    async def reconcile(self, enabled: bool) -> None:
        self.running += 1
        self.overlapped |= self.running > 1
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.installed = enabled
        self.running -= 1


@pytest.mark.parametrize("order", [(False, True), (True, False), (False, True, False)])
async def test_concurrent_memory_switches_leave_the_hooks_matching_the_final_state(
    order: tuple[bool, ...],
) -> None:
    svc = FeatureService(channel="dev", settings=_FakeSettings())
    hooks = _Hooks()
    svc.subscribe(memory_switch_subscriber(svc, hooks.reconcile))

    await asyncio.gather(*(svc.set("memory", enabled) for enabled in order))

    assert hooks.installed is svc.is_enabled("memory")
    assert not hooks.overlapped, "two switches ran their subscribers side by side"


async def test_the_memory_subscriber_reconciles_to_the_state_now_not_the_one_passed() -> None:
    """A subscriber that runs late converges on what is true when it runs."""
    svc = FeatureService(channel="dev", settings=_FakeSettings({"memory": True}))
    seen: list[bool] = []

    async def _reconcile(enabled: bool) -> None:
        seen.append(enabled)

    subscriber = memory_switch_subscriber(svc, _reconcile)
    await subscriber("memory", False)  # stale: memory is on
    await subscriber("knowledge", False)  # not memory's switch
    assert seen == [True]
