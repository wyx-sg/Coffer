"""Integration tests for TranscriptDistillationService with fake ports."""

from __future__ import annotations

import pytest

from coffer.application.distill.service import TranscriptDistillationService
from coffer.domain.distill.session import (
    DistilledInsight,
    TranscriptMessage,
    TranscriptSession,
)


class _Reader:
    def list_sessions(self, **k: object) -> list[TranscriptSession]:
        return [self._s()]

    def read_session(self, **k: object) -> TranscriptSession:
        return self._s()

    def _s(self) -> TranscriptSession:
        return TranscriptSession(
            session_id="s1",
            agent_type_value="codex",
            project_path="/repo",
            started_at=None,
            messages=(TranscriptMessage(role="user", text="why redis"),),
            source_path="/x",
        )


class _Llm:
    async def complete(self, **k: object) -> str:
        return '[{"name":"Use Redis","description":"cache","body":"Chose Redis."}]'


class _Sink:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, DistilledInsight, str]] = []

    async def record(
        self, *, project_path: str | None, insight: DistilledInsight, origin_session_id: str
    ) -> str | None:
        self.calls.append((project_path, insight, origin_session_id))
        return "2026-06-21T09:00:00+00:00"


class _Agents:
    async def resolve(self, name: str) -> tuple[str, str]:
        return ("codex", "/home/u/.codex")


class _Models:
    async def get_default(self) -> object:
        return object()

    async def get(self, mid: str) -> object:
        return object()


@pytest.mark.asyncio
async def test_distill_writes_one_journal_entry() -> None:
    sink = _Sink()
    svc = TranscriptDistillationService(
        reader=_Reader(),
        llm=_Llm(),
        sink=sink,
        agents=_Agents(),
        models=_Models(),
        credential_resolver=lambda r: "",
    )
    result = await svc.distill(agent_name="codex", session_id="s1")
    assert len(result.journal_entries) == 1
    assert sink.calls[0][0] == "/repo"
    assert sink.calls[0][2] == "s1"
    assert sink.calls[0][1].name == "Use Redis"


@pytest.mark.asyncio
async def test_distill_dry_run_writes_nothing() -> None:
    sink = _Sink()
    svc = TranscriptDistillationService(
        reader=_Reader(),
        llm=_Llm(),
        sink=sink,
        agents=_Agents(),
        models=_Models(),
        credential_resolver=lambda r: "",
    )
    result = await svc.distill(agent_name="codex", session_id="s1", dry_run=True)
    assert len(result.insights) == 1 and not sink.calls
