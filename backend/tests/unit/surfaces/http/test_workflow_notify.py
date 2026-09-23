"""``WorkflowNotify`` — an approval reaches the developer where they are.

The approval service's own suite proves it asks ``NotifyPort`` for a decision.
What it cannot prove is where that lands, because the port is a fake there.
This is the other half: the run's main thread is written first and not
best-effort, every enabled channel is told, and a channel that is down costs
the others nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from coffer.domain.chat.message import Role
from coffer.surfaces.http.workflow_adapters import WorkflowNotify


@dataclass
class _Run:
    main_conversation_id: str


class _Runs:
    def __init__(self, run: _Run | None) -> None:
        self._run = run

    async def get_run(self, run_id: str) -> _Run | None:
        return self._run


class _Chat:
    def __init__(self) -> None:
        self.appended: list[tuple[str, Role, str]] = []

    async def append_message(self, conversation_id: str, *, role: Role, content: list[Any]) -> None:
        self.appended.append((conversation_id, role, content[0].text))


@dataclass
class _Resource:
    name: str


class _Resources:
    def __init__(self, names: list[str]) -> None:
        self._names = names
        self.asked: list[tuple[str | None, bool | None]] = []

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[_Resource]:
        self.asked.append((kind, enabled))
        return [_Resource(n) for n in self._names]


class _Channels:
    def __init__(self, broken: str | None = None) -> None:
        self.sent: list[tuple[str, str]] = []
        self._broken = broken

    async def notify(self, name: str, text: str, *, actor: str) -> None:
        if name == self._broken:
            raise RuntimeError("channel is down")
        self.sent.append((name, text))


def _notify(*, chat: _Chat, channels: _Channels, resources: _Resources) -> WorkflowNotify:
    return WorkflowNotify(
        chat=cast(Any, chat),
        channels=cast(Any, channels),
        resources=cast(Any, resources),
        runs=_Runs(_Run("conv-main")),
    )


@pytest.mark.acceptance(
    spec="workflow", scenario="an approval reaches the developer where they are"
)
async def test_an_approval_lands_in_the_main_thread_and_on_every_bound_channel() -> None:
    chat, channels, resources = _Chat(), _Channels(), _Resources(["seatalk", "telegram"])

    await _notify(chat=chat, channels=channels, resources=resources).request_approval(
        "run1", "apr1", "jira__create_issue"
    )

    # The record, in the run's own thread.
    conversation, role, text = chat.appended[0]
    assert (conversation, role) == ("conv-main", Role.ASSISTANT)
    assert "apr1" in text and "jira__create_issue" in text
    # And out to the channels the developer actually has bound — only the
    # enabled ones are even asked for.
    assert resources.asked == [("channel", True)]
    assert [name for name, _ in channels.sent] == ["seatalk", "telegram"]
    assert all("apr1" in sent for _, sent in channels.sent)


async def test_a_channel_that_is_down_costs_the_others_nothing() -> None:
    chat = _Chat()
    channels = _Channels(broken="seatalk")
    resources = _Resources(["seatalk", "telegram"])

    await _notify(chat=chat, channels=channels, resources=resources).announce("run1", "started")

    assert [name for name, _ in channels.sent] == ["telegram"]
    assert len(chat.appended) == 1
