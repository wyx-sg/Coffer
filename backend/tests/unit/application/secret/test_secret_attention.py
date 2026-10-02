"""SecretAttentionSource: the approval switch, told to the Overview while off."""

from __future__ import annotations

import asyncio

from coffer.application.attention import Severity
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
