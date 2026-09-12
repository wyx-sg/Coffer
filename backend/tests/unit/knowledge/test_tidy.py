"""The tidy pass, and the one guarantee that makes it acceptable.

Tidy rewrites files a human and an agent manage together, unattended and with
no diff to approve (spec knowledge FR-050). ``.history/`` is therefore the whole
safety net, and the first test here is the one that matters: nothing is
overwritten before its prior revision is on disk.
"""

from __future__ import annotations

import pytest

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.knowledge.tidy import run_tidy
from coffer.application.knowledge.tidy_worker import TidyWorker
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import fs, paths


class _Resources:
    def __init__(self, names: list[str]) -> None:
        from datetime import UTC, datetime

        now = datetime.now(tz=UTC)
        self._rows = [
            Resource(
                id=i,
                kind=KIND_KNOWLEDGE,
                name=n,
                description=None,
                config={},
                enabled=True,
                created_at=now,
                updated_at=now,
                scope=None,
            )
            for i, n in enumerate(names, start=1)
        ]

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return list(self._rows)


class _Audit:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        self.events.append(event_type)


class _NoModel:
    async def get_default(self):  # type: ignore[no-untyped-def]
        return None


class _Model:
    def __init__(self, connection) -> None:  # type: ignore[no-untyped-def]
        self._connection = connection

    async def get_default(self):  # type: ignore[no-untyped-def]
        return self._connection


class _RewritingAgent:
    """A loop that overwrites the first file it is shown, once."""

    def __init__(self) -> None:
        self.ran = False

    async def run(self, *, model, tools, system_prompt, credential_resolver, recursion_limit):  # type: ignore[no-untyped-def]
        self.ran = True
        by_name = {t.name: t for t in tools}
        listing = await by_name["list_files"].handler({})
        first = listing["files"][0]["path"]
        await by_name["write_file"].handler(
            {"path": first, "title": "Merged", "description": "d", "body": "merged body"}
        )
        return {"ok": True}


@pytest.fixture
def service(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    fs.create_collection_dir("shopee")
    return KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="knowledge", scenario="tidy is a no-op when no internal model is configured"
)
async def test_no_internal_model_is_a_clean_noop(service) -> None:  # type: ignore[no-untyped-def]
    fs.write_file(directory="shopee", title="A", description="d", body="b")
    result = await run_tidy(
        service,
        "shopee",
        agent=_RewritingAgent(),
        models=_NoModel(),
        credential_resolver=lambda ref: "k",
    )
    assert result["status"] == "no_model"
    assert not paths.history_dir("shopee").exists()


@pytest.mark.asyncio
async def test_an_empty_collection_is_a_clean_noop(service, fake_connection) -> None:  # type: ignore[no-untyped-def]
    result = await run_tidy(
        service,
        "shopee",
        agent=_RewritingAgent(),
        models=_Model(fake_connection),
        credential_resolver=lambda ref: "k",
    )
    assert result["status"] == "empty"


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="knowledge", scenario="tidy archives the prior revision before rewriting"
)
async def test_the_prior_revision_is_archived_before_an_overwrite(  # type: ignore[no-untyped-def]
    service, fake_connection
) -> None:
    original = fs.write_file(
        directory="shopee", title="A", description="d", body="the original body"
    )
    agent = _RewritingAgent()
    result = await run_tidy(
        service,
        "shopee",
        agent=agent,
        models=_Model(fake_connection),
        credential_resolver=lambda ref: "k",
    )
    assert agent.ran and result["status"] == "ok"

    archived = sorted(paths.history_dir("shopee").glob("*.md"))
    assert len(archived) == 1
    assert "the original body" in archived[0].read_text(encoding="utf-8")
    assert fs.read_file(original.path).body.strip() == "merged body"


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="knowledge", scenario="the tidy worker stays off unless enabled")
async def test_the_worker_does_nothing_until_switched_on(service) -> None:  # type: ignore[no-untyped-def]
    """An unattended rewriter of a jointly managed corpus is something the
    operator turns on, never something they discover running (FR-051)."""
    ran: list[str] = []

    async def _tidy(svc, collection, *, actor):  # type: ignore[no-untyped-def]
        ran.append(collection)
        return {"status": "ok"}

    enabled = False

    async def _is_enabled() -> bool:
        return enabled

    async def _collections() -> list[str]:
        return ["shopee"]

    worker = TidyWorker(
        service=service, tidy=_tidy, is_enabled=_is_enabled, list_collections=_collections
    )
    await worker.run_once()
    assert ran == []

    enabled = True
    await worker.run_once()
    assert ran == ["shopee"]


@pytest.fixture
def fake_connection():  # type: ignore[no-untyped-def]
    from coffer.domain.provider.config import ProviderConfig, ResolvedConnection

    return ResolvedConnection(
        config=ProviderConfig(
            protocol="openai",
            base_url="https://example.invalid/v1",
            credential_ref="provider/test",
        ),
        model="agnes-2.0-flash",
    )
