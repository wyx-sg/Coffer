"""``MemoryHookService`` — one fire of the memory hook, at each of its two
moments (spec memory "Retrieve the notes a prompt names", "Word delivered notes
as provenance plus fact", "Audit every delivery fire").

The memory port is a fake over an in-memory corpus padded to a realistic size
(see ``_delivery_corpus``); the ledger, the ranker and the retrieval service
are the real ones. The delivery service is a recorder of
``record_fired`` calls, which is the whole of what the hook asks of it.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

import pytest

from coffer.application.memory.hook_service import HookEvent, MemoryHookService
from coffer.application.memory.retrieval import RetrievalService
from coffer.application.memory.session_ledger import SessionLedger
from coffer.domain.memory.delivery import SESSION_START, USER_PROMPT_SUBMIT
from coffer.domain.memory.hook_output import RETRIEVAL_HEADER
from coffer.domain.memory.note import TYPE_PROJECT
from coffer.domain.memory.partition import GLOBAL_PARTITION
from coffer.domain.memory.retrieval import RETRIEVAL_CEILING_BYTES
from coffer.infrastructure.memory import paths
from tests.unit.memory._delivery_corpus import FakeMemory, corpus, node20_note, note
from tests.unit.memory.conftest import FakeAudit

_AGENT = "agent-uid-1"
_PROMPT = "why does make verify fail with undici AbortSignal under node"


@dataclass
class _Delivery:
    fired: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def record_fired(self, agent_uid: str, details: dict[str, Any] | None = None) -> None:
        self.fired.append((agent_uid, dict(details or {})))


@dataclass
class _Rig:
    memory: FakeMemory
    repo: pathlib.Path
    other_repo: pathlib.Path
    delivery: _Delivery
    audit: FakeAudit
    hook: MemoryHookService

    async def fire(self, event: str, **kw: str) -> dict[str, Any] | None:
        kw.setdefault("session_id", "s1")
        kw.setdefault("cwd", str(self.repo))
        return await self.hook.handle(_AGENT, HookEvent(event=event, **kw))


@pytest.fixture
def rig(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> _Rig:
    repo = tmp_path / "work" / "coffer"
    other = tmp_path / "work" / "other"
    memory = corpus(str(repo))
    memory.partition("other", str(other))
    memory.add(node20_note("coffer"))
    ledger = SessionLedger()
    audit = FakeAudit()
    delivery = _Delivery()
    retrieval = RetrievalService(memory, ledger, signature=lambda _p: ())
    hook = MemoryHookService(
        memory=memory,
        delivery=delivery,  # type: ignore[arg-type]
        retrieval=retrieval,
    )
    return _Rig(memory, repo, other, delivery, audit, hook)


def _context(out: dict[str, Any] | None) -> str:
    assert out is not None
    return str(out["hookSpecificOutput"]["additionalContext"])


def _node20_file() -> str:
    return str(paths.notes_dir("coffer") / "node-20-for-make-verify.md")


# --- prompt-time retrieval ------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a prompt brings in the notes it names")
async def test_a_prompt_brings_in_the_note_it_names_within_the_ceiling(rig: _Rig) -> None:
    out = await rig.fire(USER_PROMPT_SUBMIT, prompt=_PROMPT)
    assert out is not None
    assert out["hookSpecificOutput"]["hookEventName"] == USER_PROMPT_SUBMIT
    text = _context(out)
    assert text.startswith(RETRIEVAL_HEADER)
    lines = text.splitlines()[1:]
    assert 1 <= len(lines) <= 3
    assert _node20_file() in lines[0]
    assert len(text.encode("utf-8")) <= RETRIEVAL_CEILING_BYTES
    # Every delivered note scored at or above the floor: the unfiltered ranking
    # says which ones did.
    _project, ranked = await rig.hook._retrieval.rank(cwd=str(rig.repo), prompt=_PROMPT)
    above = {f"{n.partition}/{n.slug}" for n, s in ranked if s >= 4.0}
    assert set(rig.delivery.fired[0][1]["notes"]) <= above


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a prompt brings in the notes it names")
async def test_at_most_three_notes_and_never_past_1500_bytes(rig: _Rig) -> None:
    for i in range(6):
        rig.memory.add(
            note(
                f"flyway-{i}",
                f"Flyway migration checksum rule {i}",
                "flyway migration checksum mismatch after editing an applied script " + "x" * 300,
                partition="coffer",
            )
        )
    out = await rig.fire(USER_PROMPT_SUBMIT, prompt="flyway migration checksum mismatch again")
    text = _context(out)
    assert 1 <= len(text.splitlines()) - 1 <= 3
    assert len(text.encode("utf-8")) <= RETRIEVAL_CEILING_BYTES


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a short or trivial prompt retrieves nothing")
async def test_a_short_or_trivial_prompt_retrieves_nothing_and_audits_nothing(rig: _Rig) -> None:
    for prompt in ("继续", "ok", "make verify"):
        assert await rig.fire(USER_PROMPT_SUBMIT, prompt=prompt) is None
    assert rig.delivery.fired == []


@pytest.mark.asyncio
async def test_a_prompt_naming_nothing_above_the_floor_delivers_nothing(rig: _Rig) -> None:
    assert await rig.fire(USER_PROMPT_SUBMIT, prompt="please rename this variable here") is None
    assert rig.delivery.fired == []


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a note already delivered in the session is not delivered again"
)
async def test_a_note_is_delivered_once_per_session_not_once_ever(rig: _Rig) -> None:
    first = _context(await rig.fire(USER_PROMPT_SUBMIT, prompt=_PROMPT, session_id="s1"))
    assert _node20_file() in first
    again = await rig.fire(USER_PROMPT_SUBMIT, prompt=_PROMPT + " again today", session_id="s1")
    assert again is None or _node20_file() not in _context(again)
    other = _context(await rig.fire(USER_PROMPT_SUBMIT, prompt=_PROMPT, session_id="s2"))
    assert _node20_file() in other


@pytest.mark.asyncio
async def test_a_prompt_in_another_repository_reads_its_own_partition_and_global(
    rig: _Rig,
) -> None:
    rig.memory.add(
        note(
            "gnu-timeout",
            "GNU timeout is gtimeout",
            "macOS has no GNU timeout; use gtimeout from coreutils",
            partition=GLOBAL_PARTITION,
        )
    )
    out = await rig.fire(
        USER_PROMPT_SUBMIT, prompt=_PROMPT + " and gtimeout coreutils", cwd=str(rig.other_repo)
    )
    text = _context(out)
    assert "gnu-timeout.md" in text
    assert _node20_file() not in text


# --- wording --------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a delivered note names its file and reads as a standing rule"
)
async def test_feedback_reads_as_a_standing_rule_and_project_as_a_recorded_fact(
    rig: _Rig,
) -> None:
    rig.memory.add(
        note(
            "node-20-in-ci",
            "CI pins Node 20 for make verify",
            "the CI workflow runs make verify on Node 20 with undici",
            partition="coffer",
            type=TYPE_PROJECT,
        )
    )
    text = _context(await rig.fire(USER_PROMPT_SUBMIT, prompt=_PROMPT))
    by_file = {line.split(")", 1)[0]: line for line in text.splitlines()[1:]}
    feedback = by_file[f"- ({_node20_file()}"]
    project = by_file[f"- ({paths.notes_dir('coffer') / 'node-20-in-ci.md'}"]
    assert pathlib.Path(_node20_file()).is_absolute()
    assert "the user's standing rule is: Run make verify under Node 20 — " in feedback
    assert "a fact they recorded: CI pins Node 20 for make verify — " in project
    for line in (feedback, project):
        assert not line.lower().split(": ", 1)[-1].startswith(("you must", "always", "never"))


# --- session start, and the audit ---------------------------------------------------


@pytest.mark.asyncio
async def test_session_start_answers_the_index_and_is_always_audited(rig: _Rig) -> None:
    out = await rig.fire(SESSION_START)
    assert out is not None
    assert out["hookSpecificOutput"]["hookEventName"] == SESSION_START
    assert "Run make verify under Node 20" in out["hookSpecificOutput"]["additionalContext"]
    assert rig.delivery.fired == [
        (_AGENT, {"moment": "session_start", "session_id": "s1", "event": SESSION_START})
    ]


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="every hook fire is recorded in the audit log")
async def test_prompt_fire_names_moment_and_notes_never_text(rig: _Rig) -> None:
    await rig.fire(USER_PROMPT_SUBMIT, prompt=_PROMPT)
    ((_a, prompt),) = rig.delivery.fired
    assert prompt["moment"] == "prompt" and prompt["session_id"] == "s1"
    assert "coffer/node-20-for-make-verify" in prompt["notes"]
    dumped = json.dumps(prompt)
    n = node20_note("coffer")
    assert n.description not in dumped and n.body.strip() not in dumped
    assert "standing rule" not in dumped


@pytest.mark.asyncio
async def test_any_other_event_answers_nothing(rig: _Rig) -> None:
    # The shell-tool moments are not Coffer's: an entry an earlier build left
    # on one of them prints nothing.
    for event in ("PreToolUse", "PostToolUse", "Stop"):
        assert await rig.fire(event) is None
    assert rig.delivery.fired == []
