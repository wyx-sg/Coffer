"""``MemoryHookService`` — one fire of the memory hook, at each of its four
moments (spec memory "Retrieve the notes a prompt names", "Guard a known trap
once per session", "Word delivered notes as provenance plus fact", "Audit
every delivery fire").

The memory port is a fake over an in-memory corpus padded to a realistic size
(see ``_delivery_corpus``); the ledger, the ranker, the retrieval service and
the trigger service are the real ones, the triggers real files under this
test's own vault directory. The delivery service is a recorder of
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
from coffer.application.memory.triggers import TriggerDraft, TriggerService
from coffer.domain.memory.delivery import (
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_START,
    USER_PROMPT_SUBMIT,
)
from coffer.domain.memory.hook_output import HELD_ONCE, RETRIEVAL_HEADER
from coffer.domain.memory.note import TYPE_FEEDBACK, TYPE_PROJECT
from coffer.domain.memory.partition import GLOBAL_PARTITION
from coffer.domain.memory.retrieval import RETRIEVAL_CEILING_BYTES
from coffer.domain.memory.trigger import KIND_CONTEXT
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
    triggers: TriggerService
    hook: MemoryHookService

    async def fire(self, event: str, **kw: str) -> dict[str, Any] | None:
        kw.setdefault("session_id", "s1")
        kw.setdefault("cwd", str(self.repo))
        if event in (PRE_TOOL_USE, POST_TOOL_USE):
            kw.setdefault("tool_name", "Bash")
        return await self.hook.handle(_AGENT, HookEvent(event=event, **kw))

    async def arm(self, note_ref: str, **kw: str) -> str:
        return (await self.triggers.add(TriggerDraft(note=note_ref, **kw), actor="user")).id


@pytest.fixture
def rig(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> _Rig:
    repo = tmp_path / "work" / "coffer"
    other = tmp_path / "work" / "other"
    memory = corpus(str(repo))
    memory.partition("other", str(other))
    memory.add(node20_note("coffer"))
    ledger = SessionLedger()
    audit = FakeAudit()
    triggers = TriggerService(audit=audit)  # type: ignore[arg-type]
    delivery = _Delivery()
    retrieval = RetrievalService(memory, ledger, signature=lambda _p: ())
    hook = MemoryHookService(
        memory=memory,
        delivery=delivery,  # type: ignore[arg-type]
        retrieval=retrieval,
        triggers=triggers,
        ledger=ledger,
    )
    return _Rig(memory, repo, other, delivery, audit, triggers, hook)


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


# --- the guard -----------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a matching command is denied once with the note as the reason"
)
async def test_a_matching_command_is_denied_once_then_passes(rig: _Rig) -> None:
    await rig.arm("coffer/node-20-for-make-verify", command=r"^make\s+verify\b", unless="v20")
    first = await rig.fire(PRE_TOOL_USE, command="make verify")
    assert first is not None
    out = first["hookSpecificOutput"]
    assert out["hookEventName"] == PRE_TOOL_USE
    assert out["permissionDecision"] == "deny"
    reason = out["permissionDecisionReason"]
    assert _node20_file() in reason
    assert "the user's standing rule is: Run make verify under Node 20" in reason
    assert reason.endswith(HELD_ONCE)
    assert await rig.fire(PRE_TOOL_USE, command="make verify") is None
    fixed = "PATH=$HOME/.nvm/versions/node/v20.20.2/bin:$PATH make verify"
    assert await rig.fire(PRE_TOOL_USE, command=fixed, session_id="fresh") is None


@pytest.mark.asyncio
async def test_an_unarmed_trigger_holds_nothing(rig: _Rig) -> None:
    tid = await rig.arm("coffer/node-20-for-make-verify", command=r"^make\s+verify\b")
    await rig.triggers.disarm(tid, actor="user")
    assert await rig.fire(PRE_TOOL_USE, command="make verify") is None


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a trigger on another repository's note stays quiet"
)
async def test_another_repositorys_trigger_stays_quiet(rig: _Rig) -> None:
    await rig.arm("coffer/node-20-for-make-verify", command=r"^make\s+verify\b")
    assert await rig.fire(PRE_TOOL_USE, command="make verify", cwd=str(rig.other_repo)) is None
    assert rig.delivery.fired == []
    # …and the same command in the note's own repository is held.
    assert await rig.fire(PRE_TOOL_USE, command="make verify") is not None


@pytest.mark.asyncio
async def test_a_global_notes_trigger_reaches_every_repository(rig: _Rig) -> None:
    rig.memory.add(
        note(
            "gnu-timeout",
            "GNU timeout is gtimeout",
            "macOS has no timeout",
            partition=GLOBAL_PARTITION,
            type=TYPE_FEEDBACK,
        )
    )
    await rig.arm("global/gnu-timeout", command=r"^timeout\b")
    for i, cwd in enumerate((rig.repo, rig.other_repo, rig.repo.parent / "not-a-repo")):
        out = await rig.fire(
            PRE_TOOL_USE, command="timeout 5 make", cwd=str(cwd), session_id=f"g{i}"
        )
        assert out is not None and out["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.asyncio
async def test_no_session_id_holds_nothing(rig: _Rig) -> None:
    await rig.arm("coffer/node-20-for-make-verify", command=r"^make\s+verify\b")
    assert await rig.fire(PRE_TOOL_USE, command="make verify", session_id="") is None
    assert rig.delivery.fired == []


@pytest.mark.asyncio
async def test_a_tool_that_is_not_the_shell_is_ignored(rig: _Rig) -> None:
    await rig.arm("coffer/node-20-for-make-verify", command=r"^make\s+verify\b")
    assert await rig.fire(PRE_TOOL_USE, command="make verify", tool_name="Write") is None
    assert await rig.fire("Stop", command="make verify") is None


@pytest.mark.asyncio
async def test_a_trigger_whose_note_is_gone_falls_back_to_its_body_or_stays_quiet(
    rig: _Rig,
) -> None:
    await rig.arm("coffer/vanished", command=r"^gradle\b", body="Run gradle with --offline.")
    out = await rig.fire(PRE_TOOL_USE, command="gradle build")
    assert out is not None
    assert "Run gradle with --offline." in out["hookSpecificOutput"]["permissionDecisionReason"]
    await rig.arm("coffer/also-gone", command=r"^mvn\b")
    assert await rig.fire(PRE_TOOL_USE, command="mvn test") is None


# --- after a command -------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="an error in a command's output adds the note without blocking"
)
async def test_an_error_adds_the_note_once_and_never_denies(rig: _Rig) -> None:
    rig.memory.add(
        note(
            "gnu-timeout",
            "GNU timeout is gtimeout",
            "macOS has no GNU timeout; use gtimeout",
            partition=GLOBAL_PARTITION,
        )
    )
    await rig.arm("global/gnu-timeout", kind=KIND_CONTEXT, error="timeout: command not found")
    output = "zsh:1: timeout: command not found"
    first = await rig.fire(POST_TOOL_USE, command="timeout 5 make", output=output)
    assert first is not None
    out = first["hookSpecificOutput"]
    assert out["hookEventName"] == POST_TOOL_USE
    assert "permissionDecision" not in out
    assert "gnu-timeout.md" in out["additionalContext"]
    assert "a fact they recorded: GNU timeout is gtimeout" in out["additionalContext"]
    assert await rig.fire(POST_TOOL_USE, command="timeout 5 make", output=output) is None
    # A context trigger never holds a command before it runs.
    assert await rig.fire(PRE_TOOL_USE, command="timeout 5 make", session_id="s9") is None


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
@pytest.mark.acceptance(
    spec="memory", scenario="a prompt and a guard fire each name their moment and notes"
)
async def test_prompt_and_guard_fires_name_moment_notes_and_trigger_never_text(
    rig: _Rig,
) -> None:
    tid = await rig.arm("coffer/node-20-for-make-verify", command=r"^make\s+verify\b")
    await rig.fire(USER_PROMPT_SUBMIT, prompt=_PROMPT)
    await rig.fire(PRE_TOOL_USE, command="make verify")
    (_a, prompt), (_b, guard) = rig.delivery.fired
    assert prompt["moment"] == "prompt" and prompt["session_id"] == "s1"
    assert "coffer/node-20-for-make-verify" in prompt["notes"]
    assert guard == {
        "moment": "guard",
        "session_id": "s1",
        "event": PRE_TOOL_USE,
        "trigger": tid,
        "notes": ["coffer/node-20-for-make-verify"],
    }
    dumped = json.dumps([prompt, guard])
    n = node20_note("coffer")
    assert n.description not in dumped and n.body.strip() not in dumped
    assert "standing rule" not in dumped


@pytest.mark.asyncio
async def test_distil_may_propose_but_never_arm(rig: _Rig) -> None:
    from coffer.domain.memory.trigger import TriggerInvalid

    proposed = await rig.triggers.propose(
        TriggerDraft(note="coffer/node-20-for-make-verify", command=r"^make\s+verify\b")
    )
    assert proposed is not None and not proposed.armed and proposed.proposed_by == "distil"
    # The same proposal twice files one trigger.
    again = await rig.triggers.propose(
        TriggerDraft(note="coffer/node-20-for-make-verify", command=r"^make\s+verify\b")
    )
    assert again is None
    with pytest.raises(TriggerInvalid):
        await rig.triggers.arm(proposed.id, actor="distil")
    assert await rig.fire(PRE_TOOL_USE, command="make verify") is None
    await rig.triggers.arm(proposed.id, actor="user")
    assert await rig.fire(PRE_TOOL_USE, command="make verify", session_id="s2") is not None
