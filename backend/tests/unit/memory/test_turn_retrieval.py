"""``TurnRetrieval`` — the per-prompt notes of a channel-driven turn (spec
memory "Retrieve the notes a prompt names for a channel turn").

The same corpus, ranker, ledger and retrieval service the hook tests use; the
agent rows and the delivery service are small fakes, since the turn needs only
the answering agent's uid and ``record_fired``.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from coffer.application.memory.hook_service import HookEvent, MemoryHookService
from coffer.application.memory.retrieval import RetrievalService
from coffer.application.memory.session_ledger import SessionLedger
from coffer.application.memory.triggers import TriggerService
from coffer.application.memory.turn_retrieval import (
    CHANNEL_TURN_EVENT,
    TurnRetrieval,
    conversation_session,
)
from coffer.domain.memory.delivery import USER_PROMPT_SUBMIT
from coffer.domain.memory.hook_output import RETRIEVAL_HEADER
from coffer.infrastructure.chat.prompt_memory import bind_prompt_memory, prompt_with_memory
from coffer.infrastructure.memory import paths
from tests.unit.memory._delivery_corpus import corpus, node20_note
from tests.unit.memory.conftest import FakeAudit

_PROMPT = "why does make verify fail with undici AbortSignal under node"


@dataclass
class _Delivery:
    fired: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def record_fired(self, agent_uid: str, details: dict[str, Any] | None = None) -> None:
        self.fired.append((agent_uid, dict(details or {})))


def _agent(uid: str, agent_type: str) -> Any:
    return SimpleNamespace(
        uid=uid,
        config={"type": agent_type, "config_dir": f"/home/u/.{agent_type}"},
    )


@dataclass
class _Agents:
    rows: list[Any]

    async def list(self) -> list[Any]:
        return self.rows


@dataclass
class _Rig:
    repo: pathlib.Path
    delivery: _Delivery
    turns: TurnRetrieval
    hook: MemoryHookService


@pytest.fixture
def rig(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> _Rig:
    monkeypatch.setenv("COFFER_MEMORY_TRIGGERS_ROOT", str(tmp_path / "vault" / "memory-triggers"))
    repo = tmp_path / "work" / "coffer"
    memory = corpus(str(repo))
    memory.add(node20_note("coffer"))
    ledger = SessionLedger()
    retrieval = RetrievalService(memory, ledger, signature=lambda _p: ())
    delivery = _Delivery()
    agents = _Agents([_agent("u-codex", "codex"), _agent("u-claude", "claude_code")])
    turns = TurnRetrieval(retrieval, delivery, agents)  # type: ignore[arg-type]
    hook = MemoryHookService(
        memory=memory,
        delivery=delivery,  # type: ignore[arg-type]
        retrieval=retrieval,
        triggers=TriggerService(audit=FakeAudit()),  # type: ignore[arg-type]
        ledger=ledger,
    )
    return _Rig(repo, delivery, turns, hook)


async def _turn(rig: _Rig, prompt: str, conversation_id: str = "c1") -> str | None:
    return await rig.turns.for_turn(
        agent_key="claude_code", cwd=str(rig.repo), prompt=prompt, conversation_id=conversation_id
    )


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a channel turn's prompt brings in the notes it names"
)
async def test_a_channel_turn_gets_what_the_hook_would_give(rig: _Rig) -> None:
    text = await _turn(rig, _PROMPT)

    assert text is not None and text.startswith(RETRIEVAL_HEADER)
    assert str(paths.notes_dir("coffer") / "node-20-for-make-verify.md") in text
    # The same answer the UserPromptSubmit hook gives a fresh session.
    out = await rig.hook.handle(
        "u-other",
        HookEvent(event=USER_PROMPT_SUBMIT, session_id="s-hook", cwd=str(rig.repo), prompt=_PROMPT),
    )
    assert out is not None and out["hookSpecificOutput"]["additionalContext"] == text
    # Audited as a prompt fire of the answering agent, keyed on the conversation.
    agent_uid, details = rig.delivery.fired[0]
    assert agent_uid == "u-claude"
    assert details["moment"] == "prompt" and details["event"] == CHANNEL_TURN_EVENT
    assert details["session_id"] == conversation_session("c1")
    assert details["notes"] == ["coffer/node-20-for-make-verify"]


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a channel turn's prompt brings in the notes it names"
)
async def test_a_conversation_is_not_given_a_note_twice(rig: _Rig) -> None:
    assert await _turn(rig, _PROMPT) is not None
    assert await _turn(rig, _PROMPT) is None
    assert await _turn(rig, _PROMPT, conversation_id="c2") is not None
    assert await _turn(rig, "继续") is None
    assert len(rig.delivery.fired) == 2


@pytest.mark.asyncio
async def test_the_prompt_carries_the_notes_after_the_users_text() -> None:
    seen: list[tuple[str, str, str, str]] = []

    async def retrieve(agent_key: str, cwd: str, prompt: str, conversation_id: str) -> str | None:
        seen.append((agent_key, cwd, prompt, conversation_id))
        return "NOTES"

    bound = bind_prompt_memory(
        retrieve, channel_uid="ch", agent_key="codex", cwd="/w", conversation_id="c9"
    )
    assert await prompt_with_memory("hello there friend", bound) == "hello there friend\n\nNOTES"
    assert seen == [("codex", "/w", "hello there friend", "c9")]
    # A turn the developer drives gets none: its own hook delivers.
    assert (
        bind_prompt_memory(retrieve, channel_uid="", agent_key="x", cwd="/w", conversation_id="c")
        is None
    )


@pytest.mark.asyncio
async def test_a_failing_retrieval_costs_the_turn_nothing_but_its_notes() -> None:
    async def broken(_prompt: str) -> str | None:
        raise RuntimeError("tree unreadable")

    assert await prompt_with_memory("hello", broken) == "hello"
    assert await prompt_with_memory("", broken) == ""
