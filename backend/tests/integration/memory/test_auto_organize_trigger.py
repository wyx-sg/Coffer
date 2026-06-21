"""Integration test: auto-organize trigger fires after store goes idle (FR-035)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

from coffer.application.memory.auto_organize import MemoryAutoOrganizer
from coffer.application.memory.organizer import OrganizerService
from coffer.domain.chat.model import ModelConfig, ProviderType
from coffer.domain.memory.scope import MemoryScope
from coffer.infrastructure.knowledge.paths import inbox_dir, topic_path


def _model() -> ModelConfig:
    now = datetime(2026, 6, 21, tzinfo=UTC)
    return ModelConfig(
        id="m1",
        display_name="Local Ollama",
        provider=ProviderType.OLLAMA,
        model="llama3",
        credential_ref=None,
        base_url="http://localhost:11434",
        is_default=True,
        created_at=now,
        updated_at=now,
    )


class _Models:
    """Fake ModelSelectorPort."""

    def __init__(self, model: ModelConfig | None) -> None:
        self._model = model

    async def get_default(self) -> ModelConfig | None:
        return self._model


class _ScriptedLlm:
    """Fake LlmCompletionPort: returns a queued raw string per call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def complete(self, *, system: str, user: str, model, credential_resolver) -> str:  # type: ignore[no-untyped-def]
        return self._responses.pop(0)


def _topic_json(slug: str, title: str, desc: str, markdown: str) -> str:
    return json.dumps(
        {
            "topic_slug": slug,
            "topic_title": title,
            "topic_description": desc,
            "markdown": markdown,
        }
    )


def _make_organizer(mem, llm: _ScriptedLlm, models: _Models) -> OrganizerService:
    svc = mem.service
    return OrganizerService(
        resolve_store=svc.resolved_store,
        get_config=svc.get_store_config,
        store_ref=svc._recall.store_ref,
        documents=mem.documents,
        retrieval=svc._retrieval,
        reconciler=svc._reconciler,
        llm=llm,
        models=models,
        credential_resolver=lambda ref: "key",
        audit=mem.audit,
        now=lambda: datetime(2026, 6, 21, 12, 0, tzinfo=UTC),
        embedding_resolver=svc._resolve_embedding,
    )


@pytest.mark.acceptance(
    spec="007-memory", scenario="memory is auto-organized after the store goes idle"
)
@pytest.mark.asyncio
async def test_auto_organize_fires_after_idle(mem) -> None:
    llm = _ScriptedLlm(
        [
            _topic_json(
                "deploy-conventions",
                "Deploy conventions",
                "how we ship",
                "# Deploy\n\nDeploy via `make release`.",
            )
        ]
    )
    organizer = _make_organizer(mem, llm, _Models(_model()))
    auto = MemoryAutoOrganizer(organize=organizer, delay_seconds=0.02)
    mem.service.set_on_change(auto.on_change)

    await mem.service.ensure_store("global")
    await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="deploy",
        description="Deploy via make release",
        body="Deploy via `make release`.",
        actor="agent",
    )
    # Wait for the debounce timer to fire
    await asyncio.sleep(0.15)

    store_dir = (await mem.service.resolved_store("global")).store_dir
    # Inbox should be drained
    assert list(inbox_dir(store_dir).glob("*.md")) == []
    # A topic doc should exist
    doc = topic_path(store_dir, "deploy-conventions")
    assert doc.exists()


@pytest.mark.asyncio
async def test_shutdown_cancels_auto_organize(mem) -> None:
    llm = _ScriptedLlm(
        [
            _topic_json(
                "deploy-conventions",
                "Deploy conventions",
                "how we ship",
                "# Deploy\n\nDeploy via `make release`.",
            )
        ]
    )
    organizer = _make_organizer(mem, llm, _Models(_model()))
    auto = MemoryAutoOrganizer(organize=organizer, delay_seconds=0.05)
    mem.service.set_on_change(auto.on_change)

    await mem.service.ensure_store("global")
    await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="deploy",
        description="Deploy via make release",
        body="Deploy via `make release`.",
        actor="agent",
    )
    # Cancel immediately before timer fires
    await auto.shutdown()
    await asyncio.sleep(0.15)

    store_dir = (await mem.service.resolved_store("global")).store_dir
    # Inbox should still have the item (organize was cancelled)
    assert len(list(inbox_dir(store_dir).glob("*.md"))) == 1
