"""Integration tests for BuiltinAgentProvider — the built-in agent's provider.

The provider is exercised with lightweight in-memory repos but a real
``ModelService`` and a real ``build_chat_model`` (constructing a LangChain
model object — no network call).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.chat.model_service import ModelService
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.model import ModelConfig, ProviderType
from coffer.domain.errors import AgentConfigRejected, NoModelConfigured
from coffer.infrastructure.chat.builtin_provider import BuiltinAgentProvider
from coffer.infrastructure.chat.langgraph_agent import LangGraphBuiltinAgent

# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------


class _AuditRepo:
    async def insert(self, entry: Any) -> None:
        return None

    async def query(self, **kwargs: Any) -> list[Any]:
        return []


class _ModelRepo:
    def __init__(self) -> None:
        self._store: dict[str, ModelConfig] = {}

    async def create(self, model: ModelConfig) -> ModelConfig:
        self._store[model.id] = model
        return model

    async def get(self, model_id: str) -> ModelConfig | None:
        return self._store.get(model_id)

    async def list(self) -> list[ModelConfig]:
        return list(self._store.values())

    async def update(self, model: ModelConfig) -> ModelConfig:
        self._store[model.id] = model
        return model

    async def delete(self, model_id: str) -> None:
        self._store.pop(model_id, None)

    async def get_default(self) -> ModelConfig | None:
        return next((m for m in self._store.values() if m.is_default), None)

    async def set_default(self, model_id: str) -> None:
        return None


class _ConvRepo:
    def __init__(self) -> None:
        self._store: dict[str, Conversation] = {}

    def add(self, conv: Conversation) -> None:
        self._store[conv.id] = conv

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._store.get(conversation_id)

    async def set_model(self, conversation_id: str, model_id: str | None) -> Conversation:
        conv = self._store[conversation_id]
        updated = Conversation(
            id=conv.id,
            agent_key=conv.agent_key,
            title=conv.title,
            model_id=model_id,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )
        self._store[conversation_id] = updated
        return updated


class _Gateway:
    async def list_tools(self) -> list[Any]:
        return []

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "coffer__list_skills":
            return {"skills": []}
        return {}


def _model(model_id: str = "m-1", *, is_default: bool = True) -> ModelConfig:
    now = datetime.now(tz=UTC)
    return ModelConfig(
        id=model_id,
        display_name=f"Model {model_id}",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref",
        base_url=None,
        is_default=is_default,
        created_at=now,
        updated_at=now,
    )


def _conversation(conv_id: str = "c-1", *, model_id: str | None = None) -> Conversation:
    now = datetime.now(tz=UTC)
    return Conversation(
        id=conv_id,
        agent_key="builtin",
        title="New conversation",
        model_id=model_id,
        created_at=now,
        updated_at=now,
    )


def _make_provider() -> tuple[BuiltinAgentProvider, _ModelRepo, _ConvRepo]:
    model_repo = _ModelRepo()
    conv_repo = _ConvRepo()
    audit = AuditService(repo=_AuditRepo())  # type: ignore[arg-type]
    model_svc = ModelService(repo=model_repo, audit=audit)  # type: ignore[arg-type]
    provider = BuiltinAgentProvider(
        model_service=model_svc,
        conversations=conv_repo,  # type: ignore[arg-type]
        tool_gateway=_Gateway(),  # type: ignore[arg-type]
        credential_resolver=lambda _ref: "fake-api-key",
    )
    return provider, model_repo, conv_repo


# ---------------------------------------------------------------------------
# init_conversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_key_is_builtin() -> None:
    provider, _, _ = _make_provider()
    assert provider.agent_key == "builtin"


@pytest.mark.asyncio
async def test_availability_is_true() -> None:
    provider, _, _ = _make_provider()
    assert await provider.availability() is True


@pytest.mark.asyncio
async def test_init_conversation_stores_a_valid_model_id() -> None:
    provider, model_repo, conv_repo = _make_provider()
    await model_repo.create(_model("m-1"))
    conv_repo.add(_conversation("c-1"))

    await provider.init_conversation("c-1", {"model_id": "m-1"})

    stored = await conv_repo.get("c-1")
    assert stored is not None
    assert stored.model_id == "m-1"


@pytest.mark.asyncio
async def test_init_conversation_no_model_id_is_a_noop() -> None:
    provider, _, conv_repo = _make_provider()
    conv_repo.add(_conversation("c-1"))

    await provider.init_conversation("c-1", {})

    stored = await conv_repo.get("c-1")
    assert stored is not None
    assert stored.model_id is None


@pytest.mark.asyncio
async def test_init_conversation_rejects_unknown_model() -> None:
    provider, _, conv_repo = _make_provider()
    conv_repo.add(_conversation("c-1"))

    with pytest.raises(AgentConfigRejected):
        await provider.init_conversation("c-1", {"model_id": "ghost"})


# ---------------------------------------------------------------------------
# build_adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_adapter_no_model_raises_no_model_configured() -> None:
    provider, _, conv_repo = _make_provider()
    conv_repo.add(_conversation("c-1"))

    with pytest.raises(NoModelConfigured):
        await provider.build_adapter("c-1")


@pytest.mark.asyncio
async def test_build_adapter_returns_a_configured_adapter() -> None:
    provider, model_repo, conv_repo = _make_provider()
    await model_repo.create(_model("m-1", is_default=True))
    conv_repo.add(_conversation("c-1"))

    adapter = await provider.build_adapter("c-1")

    assert isinstance(adapter, LangGraphBuiltinAgent)
    assert adapter.model_id == "m-1"


@pytest.mark.asyncio
async def test_build_adapter_uses_the_conversation_model_override() -> None:
    provider, model_repo, conv_repo = _make_provider()
    await model_repo.create(_model("m-default", is_default=True))
    await model_repo.create(_model("m-override", is_default=False))
    conv_repo.add(_conversation("c-1", model_id="m-override"))

    adapter = await provider.build_adapter("c-1")

    assert isinstance(adapter, LangGraphBuiltinAgent)
    assert adapter.model_id == "m-override"


# ---------------------------------------------------------------------------
# Skill catalogue parsing (malformed entries excluded)
# ---------------------------------------------------------------------------


def test_skill_catalogue_skips_malformed_entries() -> None:
    """A skill entry that is not a well-formed name/description dict is excluded
    from the catalogue the built-in agent sees, without breaking the rest."""
    from coffer.infrastructure.chat.builtin_provider import _parse_skill_catalogue

    data = {
        "skills": [
            {"name": "good-skill", "description": "a valid skill"},
            {"description": "no name — malformed"},  # missing name -> skipped
            "not-a-dict",  # wrong type -> skipped
            {"name": "another", "description": "also valid"},
        ]
    }

    catalogue = _parse_skill_catalogue(data)

    names = [s.name for s in catalogue]
    assert names == ["good-skill", "another"]


def test_skill_catalogue_handles_missing_skills_key() -> None:
    """A response with no ``skills`` list yields an empty catalogue, not an error."""
    from coffer.infrastructure.chat.builtin_provider import _parse_skill_catalogue

    assert _parse_skill_catalogue({}) == []
    assert _parse_skill_catalogue({"skills": "not-a-list"}) == []
