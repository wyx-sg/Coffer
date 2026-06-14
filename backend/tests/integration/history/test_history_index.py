"""Integration tests for the cross-agent transcript history (ADR-022).

Full real stack: the real ``FileTranscriptReader`` over real ``.jsonl`` files
(so scrubbing + tool-block dropping are genuinely exercised) feeding the real
unified ``documents``/``chunks``/FTS5 substrate under the ``transcript``
discriminator. Only a fake agent catalog (name → type + config dir) is injected.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable
from dataclasses import dataclass

import pytest
import pytest_asyncio

import coffer.infrastructure.knowledge  # noqa: F401 — register ORM + FTS5 DDL
from coffer.application.history.service import HistoryService
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.domain.errors import ResourceNotFound
from coffer.infrastructure.distill.transcript_reader import FileTranscriptReader
from coffer.infrastructure.knowledge.grep import RipgrepGrep
from coffer.infrastructure.knowledge.repository import DocumentRepo
from coffer.infrastructure.knowledge.sqlite_index import SqliteKnowledgeIndex
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

_TOOL_SECRET = "SECRET_TOOL_PAYLOAD"

# A Claude Code session: project /work/api, mentions "migration rollback".
_CLAUDE_LINES = [
    json.dumps(
        {
            "type": "user",
            "cwd": "/work/api",
            "sessionId": "claude-1",
            "timestamp": "2026-06-01T10:00:00Z",
            "message": {"role": "user", "content": "the migration rollback keeps failing"},
        }
    ),
    json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let's debug the alembic migration downgrade."},
                    {"type": "tool_use", "name": "Bash", "input": {"command": _TOOL_SECRET}},
                ],
            },
        }
    ),
]

# A Codex session: project /work/web, mentions "vitest snapshot".
_CODEX_LINES = [
    json.dumps({"type": "session_meta", "cwd": "/work/web", "id": "codex-1"}),
    json.dumps({"type": "message", "role": "user", "content": "the vitest snapshot is stale"}),
    json.dumps({"type": "message", "role": "assistant", "content": "Update the snapshot file."}),
]


def _all_files(root: pathlib.Path) -> set[pathlib.Path]:
    return {p for p in root.rglob("*") if p.is_file()}


@dataclass
class HistHarness:
    service: HistoryService
    root: pathlib.Path  # tmp root holding the DB + config dirs
    claude_jsonl: pathlib.Path


class _FakeCatalog:
    def __init__(self, mapping: dict[str, tuple[str, str]]) -> None:
        self._m = mapping

    async def list_agents(self) -> list[str]:
        return list(self._m)

    async def resolve(self, name: str) -> tuple[str, str]:
        if name not in self._m:
            raise ResourceNotFound(name)
        return self._m[name]


def _no_embed(_config: object) -> object:  # pragma: no cover - never called (keyword-only)
    raise AssertionError("history is keyword-only; embedder must not be built")


@pytest_asyncio.fixture
async def hist(tmp_path: pathlib.Path):
    db_path = tmp_path / "c.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    # Real Claude Code + Codex config dirs with real transcript files.
    claude_cfg = tmp_path / "claude_cfg"
    claude_dir = claude_cfg / "projects" / "-work-api"
    claude_dir.mkdir(parents=True)
    claude_jsonl = claude_dir / "transcript.jsonl"
    claude_jsonl.write_text("\n".join(_CLAUDE_LINES) + "\n")

    codex_cfg = tmp_path / "codex_cfg"
    codex_dir = codex_cfg / "sessions" / "2026" / "06" / "01"
    codex_dir.mkdir(parents=True)
    (codex_dir / "rollout-1.jsonl").write_text("\n".join(_CODEX_LINES) + "\n")

    documents = DocumentRepo(sm)

    def index_factory(kind: str, resource_name: str, *, dimensions):  # type: ignore[no-untyped-def]
        return SqliteKnowledgeIndex(sm, kind=kind, resource_name=resource_name, vec=None)

    retrieval = KnowledgeRetrieval(
        index_factory=index_factory,
        grep=RipgrepGrep(),
        embedder_factory=_no_embed,  # type: ignore[arg-type]
    )
    reindexer = Reindexer(embedder_factory=_no_embed)  # type: ignore[arg-type]
    catalog = _FakeCatalog(
        {
            "claude": ("claude_code", str(claude_cfg)),
            "codex": ("codex", str(codex_cfg)),
        }
    )
    service = HistoryService(
        reader=FileTranscriptReader(),
        catalog=catalog,
        documents=documents,
        retrieval=retrieval,
        reindexer=reindexer,
    )
    try:
        yield HistHarness(service=service, root=tmp_path, claude_jsonl=claude_jsonl)
    finally:
        await engine.dispose()


def _snippets(hits: Iterable) -> str:  # type: ignore[type-arg]
    return " ".join(h.snippet for h in hits)


@pytest.mark.acceptance(spec="008-agent-chat", scenario="search transcripts across agents")
@pytest.mark.asyncio
async def test_search_across_agents(hist: HistHarness) -> None:
    stats = await hist.service.rebuild()
    assert stats.indexed == 2  # one Claude + one Codex session indexed

    # A phrase only in the Claude session returns it with its agent + project.
    claude_hits = await hist.service.search("migration rollback")
    assert claude_hits, "expected a hit for the Claude session"
    top = claude_hits[0]
    assert top.agent_type == "claude_code"
    assert top.project_path == "/work/api"

    # A phrase only in the Codex session returns the Codex session.
    codex_hits = await hist.service.search("vitest snapshot")
    assert codex_hits and codex_hits[0].agent_type == "codex"

    # No tool payloads / file contents ever reach the index.
    all_text = _snippets(claude_hits) + _snippets(codex_hits)
    assert _TOOL_SECRET not in all_text

    # Filtering by agent_type narrows the corpus.
    only_codex = await hist.service.search("the", agent_type="codex")
    assert all(h.agent_type == "codex" for h in only_codex)


@pytest.mark.acceptance(spec="008-agent-chat", scenario="browse a past session read-only")
@pytest.mark.asyncio
async def test_browse_read_only(hist: HistHarness) -> None:
    before = hist.claude_jsonl.read_bytes()

    detail = await hist.service.browse(agent_name="claude", session_id="claude-1")
    roles = [t.role for t in detail.turns]
    assert "user" in roles and "assistant" in roles
    assert detail.ref.project_path == "/work/api"
    # Scrubbed turns only — the tool payload is absent.
    assert all(_TOOL_SECRET not in t.text for t in detail.turns)

    # Browsing never writes to the agent's own session store.
    assert hist.claude_jsonl.read_bytes() == before


@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="the history index is local and rebuildable"
)
@pytest.mark.asyncio
async def test_index_local_and_rebuildable(hist: HistHarness) -> None:
    files_before = _all_files(hist.root)

    await hist.service.rebuild()
    assert await hist.service.search("migration rollback")

    # Indexing writes nothing new to disk (no files-as-truth, nothing to sync):
    # the index lives in the pre-existing SQLite DB only.
    assert _all_files(hist.root) == files_before

    # Reset drops the index; search goes empty.
    removed = await hist.service.reset()
    assert removed >= 1
    assert await hist.service.search("migration rollback") == []

    # Rebuild reconstructs the identical result from the on-disk transcripts —
    # losing the index forfeits nothing durable.
    await hist.service.rebuild()
    again = await hist.service.search("migration rollback")
    assert again and again[0].session_id == "claude-1"
