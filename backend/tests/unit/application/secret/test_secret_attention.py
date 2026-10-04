"""SecretAttentionSource: the approval switch, told to the Overview while off."""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.attention import Severity, attention_key
from coffer.application.secret.attention import SecretAttentionSource
from coffer.application.secret.boundary import SecretBoundary
from tests.support.secret_boundary import FakeSealedValues, InMemoryBoundaryStore


def test_nothing_is_reported_while_the_protection_is_on() -> None:
    gate = SecretBoundary(InMemoryBoundaryStore(), FakeSealedValues())
    assert asyncio.run(SecretAttentionSource(gate.protections_on).items()) == []


def test_off_is_a_warning_whose_action_turns_it_back_on() -> None:
    gate = SecretBoundary(InMemoryBoundaryStore(), FakeSealedValues())
    gate.approve(gate.request_disable("cli").id, actor="desktop")

    [item] = asyncio.run(SecretAttentionSource(gate.protections_on).items())

    assert item.kind == "secret" and item.severity is Severity.WARNING
    assert item.reason_code == "secret_approval_off"
    assert (item.action.verb, item.action.method) == ("turn_on", "PUT")
    assert item.action.body == {"require_approval": True}


def test_turning_it_on_reports_whether_anything_changed() -> None:
    gate = SecretBoundary(InMemoryBoundaryStore(), FakeSealedValues())
    assert gate.enable_protections() is False
    gate.approve(gate.request_disable("cli").id, actor="desktop")
    assert gate.enable_protections() is True
    assert gate.protections_on()


class _Citations:
    def __init__(self, refs: list[str]) -> None:
        self._refs = refs

    async def cited_secret_refs(self) -> dict[str, list[object]]:
        return {r: [] for r in self._refs}  # type: ignore[misc]


class _Files:
    def __init__(self, stored: list[str], locked: list[str] | None = None) -> None:
        self.stored, self.locked = stored, locked or []

    def list_refs(self) -> list[tuple[str, str, str]]:
        return [(r, "", "") for r in self.stored]

    def unreadable_refs(self) -> list[str]:
        return self.locked


def _source(
    cited: list[str], stored: list[str], locked: list[str] | None = None
) -> SecretAttentionSource:
    gate = SecretBoundary(InMemoryBoundaryStore(), FakeSealedValues())
    return SecretAttentionSource(
        gate.protections_on,
        resources=_Citations(cited),  # type: ignore[arg-type]
        store=_Files(stored, locked),
        approvals=gate,
    )


@pytest.mark.acceptance(
    spec="secret", scenario="secrets with no value on this Mac are listed on Overview"
)
def test_cited_but_absent_and_unopenable_secrets_are_one_error_item() -> None:
    [item] = asyncio.run(_source(["a", "b", "c"], ["a", "c"], locked=["c"]).items())

    assert item.kind == "secret" and item.severity is Severity.ERROR
    assert item.reason_code == "secret_missing_here"
    assert item.reason == "2 secrets have no value on this Mac."
    assert (item.action.verb, item.action.method) == ("open", "GET")
    assert asyncio.run(_source(["a"], ["a"]).items()) == []


@pytest.mark.acceptance(
    spec="secret", scenario="an ignored secret item returns when the situation changes"
)
def test_the_key_changes_with_the_set_so_an_ignored_item_comes_back() -> None:
    def key(cited: list[str], stored: list[str]) -> str:
        [item] = asyncio.run(_source(cited, stored).items())
        return attention_key(item)

    one = key(["a", "b"], ["b"])
    assert key(["b", "a"], ["b"]) == one  # same set, same key
    assert key(["a", "c"], ["c"]) == one  # a different missing secret, same count
    assert key(["a", "b", "c"], ["c"]) != one  # another secret went missing


@pytest.mark.acceptance(
    spec="secret", scenario="secrets with no value on this Mac are listed on Overview"
)
def test_pending_approvals_are_one_warning_item_that_changes_with_the_set() -> None:
    gate = SecretBoundary(InMemoryBoundaryStore(), FakeSealedValues())
    source = SecretAttentionSource(gate.protections_on, approvals=gate)
    assert asyncio.run(source.items()) == []

    first = gate.request_disable("cli")
    [item] = asyncio.run(source.items())
    assert item.reason_code == "secret_approvals_pending"
    assert item.severity is Severity.WARNING
    assert item.reason == "1 change waiting for approval."
    assert (item.action.verb, item.action.method) == ("review", "GET")

    gate.reject(first.id, actor="ui")
    assert asyncio.run(source.items()) == []
