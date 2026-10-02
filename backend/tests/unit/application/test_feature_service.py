"""FeatureService: pin → setting → off, and what a switch does.

These replace the registry with three test-only features for each test, so
they never depend on the shipped four.
"""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.features import FeatureService, FeatureState
from coffer.domain.features import ExperimentalFeature, FeaturePinned, FeatureUnknown
from tests.support.features import replace_registry

_A, _B, _C = "fake_a", "fake_b", "fake_c"


@pytest.fixture(autouse=True)
def _three_fake_features(monkeypatch: pytest.MonkeyPatch) -> None:
    replace_registry(
        monkeypatch, *(ExperimentalFeature(key=k, route_prefixes=()) for k in (_A, _B, _C))
    )


def test_an_empty_registry_lists_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    replace_registry(monkeypatch)
    svc = FeatureService(settings=_FakeSettings({"vault_sync": False}))
    assert svc.list() == []
    assert svc.enabled_map() == {}


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

    def clear(self, key: str) -> None:
        if self.fail:
            raise OSError("disk full")
        self.stored.pop(key, None)


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="every experimental feature starts off",
)
def test_with_nothing_set_every_feature_is_off() -> None:
    svc = FeatureService(settings=_FakeSettings())
    assert svc.list() == [
        FeatureState(_A, False, "default"),
        FeatureState(_B, False, "default"),
        FeatureState(_C, False, "default"),
    ]
    assert svc.enabled_map() == {_A: False, _B: False, _C: False}


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a machine setting overrides the default",
)
def test_a_machine_setting_overrides_the_default() -> None:
    svc = FeatureService(settings=_FakeSettings({_C: True}))
    assert svc.state(_C) == FeatureState(_C, True, "setting")
    assert svc.state(_B) == FeatureState(_B, False, "default")
    assert svc.state(_A) == FeatureState(_A, False, "default")


def test_a_pin_overrides_the_setting() -> None:
    svc = FeatureService(
        settings=_FakeSettings({_B: True}),
        pins={_B: False},
    )
    assert svc.state(_B) == FeatureState(_B, False, "pin")
    assert svc.is_enabled(_B) is False


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a stored setting for a feature the registry does not name is ignored",
)
def test_unregistered_keys_in_settings_and_pins_are_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING")
    svc = FeatureService(
        settings=_FakeSettings({"workflow": True}),
        pins={"telemetry": True},
    )
    assert [s.key for s in svc.list()] == [_A, _B, _C]
    with pytest.raises(FeatureUnknown):
        svc.is_enabled("workflow")
    assert "workflow" in caplog.text  # ignored, but not silently


async def test_a_pinned_feature_cannot_be_switched_and_nothing_is_written() -> None:
    settings = _FakeSettings()
    svc = FeatureService(settings=settings, pins={_B: False})
    with pytest.raises(FeaturePinned):
        await svc.set(_B, True)
    assert settings.writes == []
    assert svc.is_enabled(_B) is False


async def test_set_writes_the_setting_and_changes_the_state() -> None:
    settings = _FakeSettings()
    svc = FeatureService(settings=settings)
    after = await svc.set(_A, True)
    assert after == FeatureState(_A, True, "setting")
    assert settings.writes == [(_A, True)]
    assert svc.is_enabled(_A) is True


async def test_a_failed_write_leaves_the_state_as_it_was() -> None:
    svc = FeatureService(settings=_FakeSettings(fail=True))
    with pytest.raises(OSError):
        await svc.set(_C, True)
    assert svc.state(_C) == FeatureState(_C, False, "default")


async def test_set_refuses_an_unknown_key() -> None:
    settings = _FakeSettings()
    svc = FeatureService(settings=settings)
    with pytest.raises(FeatureUnknown):
        await svc.set("workflow", True)
    assert settings.writes == []


async def test_unset_removes_the_setting_and_the_feature_is_off_again() -> None:
    settings = _FakeSettings({_C: True})
    svc = FeatureService(settings=settings)
    heard: list[tuple[str, bool]] = []
    svc.subscribe(lambda k, e: heard.append((k, e)))

    after = await svc.unset(_C)

    assert after == FeatureState(_C, False, "default")
    assert _C not in settings.stored
    assert heard == [(_C, False)]
    # Unsetting again changes nothing and is not an error.
    assert await svc.unset(_C) == FeatureState(_C, False, "default")
    assert heard == [(_C, False)]


async def test_unset_refuses_a_pinned_or_unknown_feature_and_writes_nothing() -> None:
    settings = _FakeSettings({_B: True})
    svc = FeatureService(settings=settings, pins={_B: True})
    with pytest.raises(FeaturePinned):
        await svc.unset(_B)
    with pytest.raises(FeatureUnknown):
        await svc.unset("workflow")
    assert settings.stored == {_B: True}


async def test_a_failed_unset_leaves_the_state_as_it_was() -> None:
    settings = _FakeSettings({_C: True})
    settings.fail = True
    svc = FeatureService(settings=settings)
    with pytest.raises(OSError):
        await svc.unset(_C)
    assert svc.state(_C) == FeatureState(_C, True, "setting")


async def test_subscribers_hear_a_change_sync_and_async() -> None:
    svc = FeatureService(settings=_FakeSettings())
    heard_sync: list[tuple[str, bool]] = []
    heard_async: list[tuple[str, bool]] = []

    def on_sync(key: str, enabled: bool) -> None:
        heard_sync.append((key, enabled))

    async def on_async(key: str, enabled: bool) -> None:
        heard_async.append((key, enabled))

    svc.subscribe(on_sync)
    svc.subscribe(on_async)
    await svc.set(_C, True)
    assert heard_sync == [(_C, True)]
    assert heard_async == [(_C, True)]


async def test_subscribers_hear_nothing_when_the_state_does_not_move() -> None:
    """Writing `off` over the `off` default records a setting but is no change."""
    settings = _FakeSettings()
    svc = FeatureService(settings=settings)
    heard: list[tuple[str, bool]] = []
    svc.subscribe(lambda k, e: heard.append((k, e)))
    after = await svc.set(_B, False)
    assert after.source == "setting"
    assert settings.writes == [(_B, False)]
    assert heard == []


async def test_a_failing_subscriber_does_not_stop_the_others() -> None:
    svc = FeatureService(settings=_FakeSettings())
    heard: list[str] = []

    def broken(key: str, enabled: bool) -> None:
        raise RuntimeError("boom")

    svc.subscribe(broken)
    svc.subscribe(lambda k, e: heard.append(k))
    after = await svc.set(_A, True)
    assert after.enabled is True
    assert heard == [_A]


class _Hooks:
    """Stands in for something a switch reconciles: the reconcile yields to the
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
async def test_concurrent_switches_run_their_subscribers_one_at_a_time(
    order: tuple[bool, ...],
) -> None:
    """A subscriber that reconciles to the state as it is when it runs ends on
    the final state, because two switches never run their subscribers side by
    side."""
    svc = FeatureService(settings=_FakeSettings({_C: True}))
    hooks = _Hooks()

    async def _on_switch(key: str, _enabled: bool) -> None:
        if key == _C:
            await hooks.reconcile(svc.is_enabled(_C))

    svc.subscribe(_on_switch)

    await asyncio.gather(*(svc.set(_C, enabled) for enabled in order))

    assert hooks.installed is svc.is_enabled(_C)
    assert not hooks.overlapped, "two switches ran their subscribers side by side"
