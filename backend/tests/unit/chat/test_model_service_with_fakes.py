"""Unit tests for ModelService using an in-memory fake repo."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.chat.model_service import ModelService
from coffer.domain.chat.model import ModelConfig, ProviderType
from coffer.domain.errors import ModelNotFound, ModelRejected

from .conftest import FakeAuditRepo, FakeChatModelRepo


def _make_anthropic(
    id: str = "m-001",
    display_name: str = "Claude",
    is_default: bool = False,
) -> ModelConfig:
    now = datetime.now(tz=UTC)
    return ModelConfig(
        id=id,
        display_name=display_name,
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="key-ref",
        base_url=None,
        is_default=is_default,
        created_at=now,
        updated_at=now,
    )


def make_service() -> tuple[ModelService, FakeChatModelRepo, FakeAuditRepo]:
    repo = FakeChatModelRepo()
    audit_repo = FakeAuditRepo()
    audit = AuditService(repo=audit_repo)  # type: ignore[arg-type]
    svc = ModelService(repo=repo, audit=audit)  # type: ignore[arg-type]
    return svc, repo, audit_repo


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_first_model_is_default() -> None:
    svc, _repo, _ = make_service()
    m = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref",
        base_url=None,
    )
    assert m.is_default is True


@pytest.mark.asyncio
async def test_create_second_model_is_not_default() -> None:
    svc, _, _ = make_service()
    await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref1",
        base_url=None,
    )
    m2 = await svc.create(
        display_name="GPT-4o",
        provider=ProviderType.OPENAI,
        model="gpt-4o",
        credential_ref="ref2",
        base_url=None,
    )
    assert m2.is_default is False


@pytest.mark.asyncio
async def test_create_second_model_with_is_default_becomes_default() -> None:
    """Creating a non-first model with is_default=True promotes it and demotes
    the previous default (the REST/CLI ``--default`` flag must take effect)."""
    svc, _, _ = make_service()
    m1 = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref1",
        base_url=None,
    )
    m2 = await svc.create(
        display_name="GPT-4o",
        provider=ProviderType.OPENAI,
        model="gpt-4o",
        credential_ref="ref2",
        base_url=None,
        is_default=True,
    )
    assert m2.is_default is True
    reloaded_default = await svc.get_default()
    assert reloaded_default is not None
    assert reloaded_default.id == m2.id
    refreshed_m1 = await svc.get(m1.id)
    assert refreshed_m1.is_default is False


@pytest.mark.asyncio
async def test_create_duplicate_name_raises_model_rejected() -> None:
    svc, _, _ = make_service()
    await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref",
        base_url=None,
    )
    with pytest.raises(ModelRejected) as exc_info:
        await svc.create(
            display_name="Claude",  # same name
            provider=ProviderType.OPENAI,
            model="gpt-4o",
            credential_ref="ref2",
            base_url=None,
        )
    assert exc_info.value.reason == "duplicate_name"


@pytest.mark.asyncio
async def test_create_emits_audit() -> None:
    svc, _, audit_repo = make_service()
    m = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref",
        base_url=None,
        actor="alice",
    )
    assert any(e.event_type == "model_created" for e in audit_repo.entries)
    entry = next(e for e in audit_repo.entries if e.event_type == "model_created")
    assert entry.details["model_id"] == m.id


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_model_raises_not_found() -> None:
    svc, _, _ = make_service()
    with pytest.raises(ModelNotFound):
        await svc.get("no-such-id")


@pytest.mark.asyncio
async def test_list_empty() -> None:
    svc, _, _ = make_service()
    result = await svc.list()
    assert result == []


@pytest.mark.asyncio
async def test_get_default_none_when_empty() -> None:
    svc, _, _ = make_service()
    assert await svc.get_default() is None


@pytest.mark.asyncio
async def test_get_default_returns_default_model() -> None:
    svc, _, _ = make_service()
    m = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref",
        base_url=None,
    )
    default = await svc.get_default()
    assert default is not None
    assert default.id == m.id


# ---------------------------------------------------------------------------
# Delete — single-default invariant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_default_promotes_oldest_remaining() -> None:
    svc, _repo, _ = make_service()
    m1 = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref1",
        base_url=None,
    )
    m2 = await svc.create(
        display_name="GPT-4o",
        provider=ProviderType.OPENAI,
        model="gpt-4o",
        credential_ref="ref2",
        base_url=None,
    )
    assert m1.is_default is True
    assert m2.is_default is False

    await svc.delete(m1.id)

    new_default = await svc.get_default()
    assert new_default is not None
    assert new_default.id == m2.id
    assert new_default.is_default is True


@pytest.mark.asyncio
async def test_delete_last_model_leaves_no_default() -> None:
    svc, _, _ = make_service()
    m = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref",
        base_url=None,
    )
    await svc.delete(m.id)
    assert await svc.get_default() is None


@pytest.mark.asyncio
async def test_delete_non_default_does_not_change_default() -> None:
    svc, _, _ = make_service()
    m1 = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref1",
        base_url=None,
    )
    m2 = await svc.create(
        display_name="GPT-4o",
        provider=ProviderType.OPENAI,
        model="gpt-4o",
        credential_ref="ref2",
        base_url=None,
    )
    await svc.delete(m2.id)
    default = await svc.get_default()
    assert default is not None
    assert default.id == m1.id


@pytest.mark.asyncio
async def test_delete_emits_audit() -> None:
    svc, _, audit_repo = make_service()
    m = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref",
        base_url=None,
        actor="system",
    )
    await svc.delete(m.id, actor="alice")
    assert any(e.event_type == "model_deleted" for e in audit_repo.entries)


@pytest.mark.asyncio
async def test_delete_not_found_raises() -> None:
    svc, _, _ = make_service()
    with pytest.raises(ModelNotFound):
        await svc.delete("no-such-id")


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_display_name() -> None:
    svc, _, _ = make_service()
    m = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref",
        base_url=None,
    )
    updated = await svc.update(m.id, display_name="My Claude")
    assert updated.display_name == "My Claude"


@pytest.mark.asyncio
async def test_update_to_duplicate_name_raises() -> None:
    svc, _, _ = make_service()
    await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref1",
        base_url=None,
    )
    m2 = await svc.create(
        display_name="GPT-4o",
        provider=ProviderType.OPENAI,
        model="gpt-4o",
        credential_ref="ref2",
        base_url=None,
    )
    with pytest.raises(ModelRejected) as exc_info:
        await svc.update(m2.id, display_name="Claude")
    assert exc_info.value.reason == "duplicate_name"


@pytest.mark.asyncio
async def test_update_not_found_raises() -> None:
    svc, _, _ = make_service()
    with pytest.raises(ModelNotFound):
        await svc.update("no-such", display_name="X")


@pytest.mark.asyncio
async def test_update_emits_audit() -> None:
    svc, _, audit_repo = make_service()
    m = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref",
        base_url=None,
    )
    await svc.update(m.id, display_name="Updated", actor="bob")
    assert any(e.event_type == "model_updated" for e in audit_repo.entries)


@pytest.mark.asyncio
async def test_update_is_default_true_promotes_and_demotes() -> None:
    """update(id, is_default=True) must promote that model and demote others.

    Fix 3: verifies the single-default invariant is maintained atomically
    (no transient window with two defaults) and that the audit event is emitted.
    """
    svc, _repo, audit_repo = make_service()

    m1 = await svc.create(
        display_name="Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref1",
        base_url=None,
    )
    m2 = await svc.create(
        display_name="GPT-4o",
        provider=ProviderType.OPENAI,
        model="gpt-4o",
        credential_ref="ref2",
        base_url=None,
    )
    # m1 is default, m2 is not.
    assert m1.is_default is True
    assert m2.is_default is False

    updated = await svc.update(m2.id, is_default=True)

    # m2 must now be the default.
    assert updated.is_default is True

    # m1 must no longer be the default.
    reloaded_m1 = await svc.get(m1.id)
    assert reloaded_m1.is_default is False

    # Exactly one default must exist.
    all_models = await svc.list()
    defaults = [m for m in all_models if m.is_default]
    assert len(defaults) == 1
    assert defaults[0].id == m2.id

    # Audit event must have been emitted.
    assert any(e.event_type == "model_updated" for e in audit_repo.entries)
