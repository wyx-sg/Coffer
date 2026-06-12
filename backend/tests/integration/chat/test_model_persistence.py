"""Integration tests for ChatModelRepo against real SQLite.

Covers:
- model create / get / list / update / delete
- get_default / set_default (atomic single-default invariant)
- provider string coercion to ProviderType
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from coffer.domain.chat.model import ModelConfig, ProviderType
from coffer.domain.errors import ModelNotFound
from coffer.infrastructure.chat.model_persistence import ChatModelRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


async def _setup(tmp_path):  # type: ignore[no-untyped-def]
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'm.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    return engine, ChatModelRepo(sm)


def _anthropic_model(
    display_name: str = "Claude Sonnet",
    is_default: bool = False,
) -> ModelConfig:
    now = datetime.now(tz=UTC)
    return ModelConfig(
        id=uuid.uuid4().hex,
        display_name=display_name,
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="keychain-ref",
        base_url=None,
        is_default=is_default,
        created_at=now,
        updated_at=now,
    )


def _ollama_model(
    display_name: str = "Llama 3",
    is_default: bool = False,
) -> ModelConfig:
    now = datetime.now(tz=UTC)
    return ModelConfig(
        id=uuid.uuid4().hex,
        display_name=display_name,
        provider=ProviderType.OLLAMA,
        model="llama3.1",
        credential_ref=None,
        base_url="http://localhost:11434",
        is_default=is_default,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="008-agent-chat", scenario="register a model provider")
async def test_create_and_get_model(tmp_path):  # type: ignore[no-untyped-def]
    engine, repo = await _setup(tmp_path)
    try:
        m = _anthropic_model("My Model")
        created = await repo.create(m)
        assert created.id == m.id
        assert created.display_name == "My Model"
        assert created.provider == ProviderType.ANTHROPIC

        fetched = await repo.get(m.id)
        assert fetched is not None
        assert fetched.id == m.id
        assert fetched.provider == ProviderType.ANTHROPIC
    finally:
        await engine.dispose()


async def test_create_duplicate_name_raises_model_rejected(tmp_path):  # type: ignore[no-untyped-def]
    """A unique-constraint violation on display_name surfaces as the domain
    ``ModelRejected`` (-> 400), not a raw IntegrityError (-> 500)."""
    from coffer.domain.errors import ModelRejected

    engine, repo = await _setup(tmp_path)
    try:
        await repo.create(_anthropic_model("Same Name"))
        with pytest.raises(ModelRejected):
            await repo.create(_ollama_model("Same Name"))
    finally:
        await engine.dispose()


async def test_update_duplicate_name_raises_model_rejected(tmp_path):  # type: ignore[no-untyped-def]
    """Renaming a model onto an existing display_name surfaces as ModelRejected
    (-> 400) even when the service-level pre-check loses the race — the unique
    constraint is the authoritative gate on update() as well as create()."""
    import dataclasses

    from coffer.domain.errors import ModelRejected

    engine, repo = await _setup(tmp_path)
    try:
        await repo.create(_anthropic_model("Taken"))
        m2 = await repo.create(_ollama_model("Free"))
        with pytest.raises(ModelRejected):
            await repo.update(dataclasses.replace(m2, display_name="Taken"))
    finally:
        await engine.dispose()


async def test_get_missing_model_returns_none(tmp_path):  # type: ignore[no-untyped-def]
    engine, repo = await _setup(tmp_path)
    try:
        result = await repo.get("no-such-id")
        assert result is None
    finally:
        await engine.dispose()


async def test_list_models(tmp_path):  # type: ignore[no-untyped-def]
    engine, repo = await _setup(tmp_path)
    try:
        m1 = await repo.create(_anthropic_model("M1"))
        m2 = await repo.create(_ollama_model("M2"))

        all_models = await repo.list()
        ids = {m.id for m in all_models}
        assert m1.id in ids
        assert m2.id in ids
    finally:
        await engine.dispose()


async def test_update_model(tmp_path):  # type: ignore[no-untyped-def]
    engine, repo = await _setup(tmp_path)
    try:
        m = await repo.create(_anthropic_model("Original"))
        now = datetime.now(tz=UTC)
        updated_domain = ModelConfig(
            id=m.id,
            display_name="Renamed",
            provider=m.provider,
            model="claude-opus-4",
            credential_ref=m.credential_ref,
            base_url=m.base_url,
            is_default=m.is_default,
            created_at=m.created_at,
            updated_at=now,
        )
        saved = await repo.update(updated_domain)
        assert saved.display_name == "Renamed"
        assert saved.model == "claude-opus-4"
    finally:
        await engine.dispose()


async def test_delete_model(tmp_path):  # type: ignore[no-untyped-def]
    engine, repo = await _setup(tmp_path)
    try:
        m = await repo.create(_anthropic_model())
        await repo.delete(m.id)

        result = await repo.get(m.id)
        assert result is None
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Default invariant tests
# ---------------------------------------------------------------------------


async def test_get_default_returns_none_when_empty(tmp_path):  # type: ignore[no-untyped-def]
    engine, repo = await _setup(tmp_path)
    try:
        result = await repo.get_default()
        assert result is None
    finally:
        await engine.dispose()


async def test_set_default_single_model(tmp_path):  # type: ignore[no-untyped-def]
    engine, repo = await _setup(tmp_path)
    try:
        m = await repo.create(_anthropic_model(is_default=True))
        default = await repo.get_default()
        assert default is not None
        assert default.id == m.id
    finally:
        await engine.dispose()


async def test_set_default_switches_between_models(tmp_path):  # type: ignore[no-untyped-def]
    engine, repo = await _setup(tmp_path)
    try:
        m1 = await repo.create(_anthropic_model("M1", is_default=True))
        m2 = await repo.create(_ollama_model("M2", is_default=False))

        # Initially m1 is default.
        d = await repo.get_default()
        assert d is not None
        assert d.id == m1.id

        # Set m2 as default.
        await repo.set_default(m2.id)
        d2 = await repo.get_default()
        assert d2 is not None
        assert d2.id == m2.id

        # m1 must no longer be default.
        m1_fetched = await repo.get(m1.id)
        assert m1_fetched is not None
        assert m1_fetched.is_default is False
    finally:
        await engine.dispose()


async def test_set_default_only_one_default(tmp_path):  # type: ignore[no-untyped-def]
    """After set_default, exactly one model has is_default=True."""
    engine, repo = await _setup(tmp_path)
    try:
        await repo.create(_anthropic_model("M1", is_default=True))
        await repo.create(_ollama_model("M2", is_default=False))
        m3 = await repo.create(_anthropic_model("M3"))

        await repo.set_default(m3.id)
        all_models = await repo.list()
        defaults = [m for m in all_models if m.is_default]
        assert len(defaults) == 1
        assert defaults[0].id == m3.id
    finally:
        await engine.dispose()


async def test_set_default_does_not_touch_unrelated_rows(tmp_path):  # type: ignore[no-untyped-def]
    """Promoting one model must not bump ``updated_at`` on models that were
    neither the old default nor the new one."""
    engine, repo = await _setup(tmp_path)
    try:
        await repo.create(_anthropic_model("M1", is_default=True))
        m2 = await repo.create(_ollama_model("M2", is_default=False))
        m3 = await repo.create(_anthropic_model("M3", is_default=False))

        before = (await repo.get(m3.id)).updated_at  # type: ignore[union-attr]
        await repo.set_default(m2.id)
        after = (await repo.get(m3.id)).updated_at  # type: ignore[union-attr]

        assert after == before  # M3 was untouched by the promotion
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Provider coercion tests
# ---------------------------------------------------------------------------


async def test_provider_coercion(tmp_path):  # type: ignore[no-untyped-def]
    """Model read back from DB yields a proper ProviderType enum, not a raw string."""
    engine, repo = await _setup(tmp_path)
    try:
        m = await repo.create(_ollama_model())
        fetched = await repo.get(m.id)
        assert fetched is not None
        assert isinstance(fetched.provider, ProviderType)
        assert fetched.provider == ProviderType.OLLAMA
    finally:
        await engine.dispose()


async def test_all_provider_types_round_trip(tmp_path):  # type: ignore[no-untyped-def]
    """All three provider types survive a DB round-trip."""
    engine, repo = await _setup(tmp_path)
    try:
        for provider, kwargs in [
            (ProviderType.ANTHROPIC, {"credential_ref": "ref", "base_url": None}),
            (ProviderType.OPENAI, {"credential_ref": "ref2", "base_url": None}),
            (ProviderType.OLLAMA, {"credential_ref": None, "base_url": "http://localhost:11434"}),
        ]:
            now = datetime.now(tz=UTC)
            m = ModelConfig(
                id=uuid.uuid4().hex,
                display_name=f"model-{provider}",
                provider=provider,
                model="some-model",
                is_default=False,
                created_at=now,
                updated_at=now,
                **kwargs,
            )
            created = await repo.create(m)
            fetched = await repo.get(created.id)
            assert fetched is not None
            assert fetched.provider == provider
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Domain error boundary tests (hardening)
# ---------------------------------------------------------------------------


async def test_update_missing_model_raises_domain_error(tmp_path):  # type: ignore[no-untyped-def]
    """ChatModelRepo.update on a non-existent id raises ModelNotFound."""
    engine, repo = await _setup(tmp_path)
    try:
        now = datetime.now(tz=UTC)
        ghost = ModelConfig(
            id="ghost-id-that-does-not-exist",
            display_name="Ghost",
            provider=ProviderType.ANTHROPIC,
            model="claude-sonnet-4-6",
            credential_ref="ref",
            base_url=None,
            is_default=False,
            created_at=now,
            updated_at=now,
        )
        with pytest.raises(ModelNotFound) as exc_info:
            await repo.update(ghost)
        assert exc_info.value.model_id == "ghost-id-that-does-not-exist"
    finally:
        await engine.dispose()
