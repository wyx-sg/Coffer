import pytest
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    ConfigValidationError,
    ResourceAlreadyExists,
    ResourceNotFound,
    UnknownKind,
)
from coffer.domain.resource import Kind, ResourceRef
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)


class _FakeConfig(BaseModel):
    foo: int
    bar: str = "default"


async def _service(tmp_path, *, kinds=None, on_delete=None):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    if kinds is None:
        kinds = {
            "fake_kind": Kind(
                name="fake_kind",
                display_name="Fake Kind",
                config_schema=_FakeConfig,
                on_delete=on_delete,
            ),
        }
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    return ResourceService(kinds=kinds, repo=repo, audit=audit), audit, engine


@pytest.mark.asyncio
async def test_register_persists_and_audits(tmp_path):
    svc, audit, engine = await _service(tmp_path)
    r = await svc.register(
        kind="fake_kind",
        name="t",
        config={"foo": 1, "bar": "hello"},
        description="test resource",
        actor="cli",
    )
    assert r.id != 0
    assert r.kind == "fake_kind"
    assert r.config == {"foo": 1, "bar": "hello"}
    assert r.enabled is True

    # Audit recorded
    entries = await audit.query(event_type=AuditEventType.RESOURCE_CREATED.value)
    assert len(entries) == 1
    assert entries[0].resource_kind == "fake_kind"
    assert entries[0].resource_name == "t"
    assert entries[0].actor == "cli"
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_validates_via_schema(tmp_path):
    svc, _, engine = await _service(tmp_path)
    with pytest.raises(ConfigValidationError):
        await svc.register(
            kind="fake_kind",
            name="t",
            config={"foo": "not_an_int"},
            actor="cli",
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_generic_register_rejects_lifecycle_kind(tmp_path):
    """CODE-REG: a kind that owns creation invariants (master folder, agent
    detection) must declare ``generic_create_allowed=False`` so the generic
    POST /resources path cannot create a half-formed row behind its back. The
    kind-owning service opts in via ``allow_lifecycle_kind=True``.
    """
    from coffer.domain.errors import GenericCreateNotAllowed

    kinds = {
        "skill": Kind(
            name="skill",
            display_name="Skill",
            config_schema=_FakeConfig,
            generic_create_allowed=False,
        ),
    }
    svc, _, engine = await _service(tmp_path, kinds=kinds)
    try:
        # Generic path (no opt-in) is rejected.
        with pytest.raises(GenericCreateNotAllowed):
            await svc.register(kind="skill", name="t", config={"foo": 1}, actor="cli")
        # Kind-owning service path succeeds.
        r = await svc.register(
            kind="skill",
            name="t",
            config={"foo": 1},
            actor="skill-service",
            allow_lifecycle_kind=True,
        )
        assert r.id != 0

        # The same guard covers UPDATE: a generic PATCH must not rewrite a
        # lifecycle kind's config behind its owning service (the row would
        # desync from the on-disk artifact). The owning service opts in.
        with pytest.raises(GenericCreateNotAllowed):
            await svc.update_config(ResourceRef("skill", "t"), new_config={"foo": 2}, actor="cli")
        updated = await svc.update_config(
            ResourceRef("skill", "t"),
            new_config={"foo": 2},
            actor="skill-service",
            allow_lifecycle_kind=True,
        )
        assert updated.config["foo"] == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_kind_supplied_credential_extractor_and_audit_redactor(tmp_path):
    """CODE-006/ADR-001: ResourceService must NOT hardcode the mcp_server
    ``transport`` config shape. A kind supplies its own credential-ref
    extractor (probed before any DB write) and audit redactor (secrets stripped
    before audit), and the kind-agnostic core just calls them — proven here with
    a kind that stores its ref/secret OUTSIDE any ``transport`` key.
    """
    from coffer.domain.audit import AuditEventType
    from coffer.domain.errors import CredentialMissing

    class _SecretConfig(BaseModel):
        secret_ref: str
        plaintext: str = ""

    class _FakeKeyring:
        def __init__(self, present: set[str]) -> None:
            self._present = present

        def get(self, ref: str) -> str | None:
            return "value" if ref in self._present else None

    kinds = {
        "vault": Kind(
            name="vault",
            display_name="Vault",
            config_schema=_SecretConfig,
            credential_ref_extractor=lambda cfg: {"secret": cfg["secret_ref"]},
            audit_redactor=lambda cfg: {k: v for k, v in cfg.items() if k != "plaintext"},
        ),
    }

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    try:
        # Missing credential → probe fails before any DB write.
        svc_missing = ResourceService(
            kinds=kinds,
            repo=SqlAlchemyResourceRepo(sm),
            audit=audit,
            credentials=_FakeKeyring(present=set()),
        )
        with pytest.raises(CredentialMissing):
            await svc_missing.register(
                kind="vault", name="t", config={"secret_ref": "k1"}, actor="cli"
            )

        # Present credential → succeeds; audit drops the redacted field.
        svc_ok = ResourceService(
            kinds=kinds,
            repo=SqlAlchemyResourceRepo(sm),
            audit=audit,
            credentials=_FakeKeyring(present={"k1"}),
        )
        await svc_ok.register(
            kind="vault",
            name="t",
            config={"secret_ref": "k1", "plaintext": "leak-me"},
            actor="cli",
        )
        entries = await audit.query(event_type=AuditEventType.RESOURCE_CREATED.value)
        created = [e for e in entries if e.resource_name == "t"]
        assert created, "expected a RESOURCE_CREATED audit entry"
        assert "plaintext" not in created[0].details["config"]
        assert created[0].details["config"]["secret_ref"] == "k1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_register_unknown_kind_raises(tmp_path):
    svc, _, engine = await _service(tmp_path)
    with pytest.raises(UnknownKind):
        await svc.register(kind="nope", name="x", config={}, actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_duplicate_raises(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    with pytest.raises(ResourceAlreadyExists):
        await svc.register(kind="fake_kind", name="t", config={"foo": 2}, actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_and_get(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.register(kind="fake_kind", name="a", config={"foo": 1}, actor="cli")
    await svc.register(kind="fake_kind", name="b", config={"foo": 2}, actor="cli")

    all_resources = await svc.list()
    assert {r.name for r in all_resources} == {"a", "b"}

    r = await svc.get(ResourceRef("fake_kind", "a"))
    assert r.config == {"foo": 1, "bar": "default"}

    with pytest.raises(ResourceNotFound):
        await svc.get(ResourceRef("fake_kind", "nope"))
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_config_audits_with_before_after(tmp_path):
    svc, audit, engine = await _service(tmp_path)
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    await svc.update_config(
        ResourceRef("fake_kind", "t"),
        new_config={"foo": 2, "bar": "different"},
        actor="api",
        description="changed",
    )
    entries = await audit.query(event_type=AuditEventType.RESOURCE_UPDATED.value)
    assert len(entries) == 1
    assert entries[0].actor == "api"
    assert entries[0].details["before"] == {"foo": 1, "bar": "default"}
    assert entries[0].details["after"] == {"foo": 2, "bar": "different"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_set_enabled_is_idempotent_and_audits_only_on_change(tmp_path):
    svc, audit, engine = await _service(tmp_path)
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")

    # idempotent: enabling an already-enabled resource doesn't audit
    await svc.set_enabled(ResourceRef("fake_kind", "t"), True, actor="api")
    enabled_events = await audit.query(event_type=AuditEventType.RESOURCE_ENABLED.value)
    assert len(enabled_events) == 0

    await svc.set_enabled(ResourceRef("fake_kind", "t"), False, actor="api")
    disabled_events = await audit.query(event_type=AuditEventType.RESOURCE_DISABLED.value)
    assert len(disabled_events) == 1
    assert disabled_events[0].actor == "api"
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_invokes_on_delete_hook_and_audits(tmp_path):
    calls: list[ResourceRef] = []
    svc, audit, engine = await _service(tmp_path, on_delete=lambda ref: calls.append(ref))
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    await svc.delete(ResourceRef("fake_kind", "t"), actor="cli")
    assert calls == [ResourceRef("fake_kind", "t")]
    assert await svc.list() == []

    entries = await audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert len(entries) == 1
    assert entries[0].details.get("snapshot") is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_aborts_when_on_delete_raises(tmp_path):
    def boom(ref: ResourceRef) -> None:
        raise RuntimeError("cleanup failed")

    svc, audit, engine = await _service(tmp_path, on_delete=boom)
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await svc.delete(ResourceRef("fake_kind", "t"), actor="cli")

    # Resource still exists
    r = await svc.get(ResourceRef("fake_kind", "t"))
    assert r.name == "t"
    # No deletion audit entry
    entries = await audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert entries == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_unknown_resource_raises(tmp_path):
    svc, _, engine = await _service(tmp_path)
    with pytest.raises(ResourceNotFound):
        await svc.delete(ResourceRef("fake_kind", "nope"), actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_kb_and_memory_credential_extractors_probe_missing_refs(tmp_path):
    """The KB kind (nested ``embedding.credential_ref``) and memory kind (flat
    ``embedding_credential_ref``) supply credential extractors; a missing
    keychain entry must fail register/PATCH BEFORE any DB write (rebase
    follow-up: the extractors previously executed in zero tests)."""
    from coffer.application.knowledge_base.kind import make_kb_kind
    from coffer.application.memory.kind import make_memory_kind
    from coffer.domain.errors import CredentialMissing, ResourceNotFound
    from coffer.domain.resource import ResourceRef

    class _FakeKeyring:
        def __init__(self, present: set[str]) -> None:
            self._present = present

        def get(self, ref: str) -> str | None:
            return "value" if ref in self._present else None

    # The extractor functions never touch the wrapped service, so the kinds can
    # be built without one for register-time probing.
    kinds = {
        "knowledge_base": make_kb_kind(None),  # type: ignore[arg-type]
        "memory": make_memory_kind(None),  # type: ignore[arg-type]
    }
    kb_config = {
        "enabled_modes": ["keyword", "grep", "vector"],
        "default_mode": "keyword",
        "embedding": {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "dimensions": 1536,
            "credential_ref": "openai-key",
        },
    }
    mem_config = {
        "retrieval_modes": ["grep", "keyword", "vector"],
        "default_mode": "keyword",
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
        "embedding_credential_ref": "openai-key",
    }

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    repo = SqlAlchemyResourceRepo(sm)
    try:
        svc_missing = ResourceService(
            kinds=kinds, repo=repo, audit=audit, keyring=_FakeKeyring(present=set())
        )
        with pytest.raises(CredentialMissing):
            await svc_missing.register(
                kind="knowledge_base", name="kb1", config=kb_config, actor="cli"
            )
        with pytest.raises(CredentialMissing):
            await svc_missing.register(kind="memory", name="global", config=mem_config, actor="cli")
        # Nothing was written.
        with pytest.raises(ResourceNotFound):
            await svc_missing.get(ResourceRef("knowledge_base", "kb1"))
        with pytest.raises(ResourceNotFound):
            await svc_missing.get(ResourceRef("memory", "global"))

        svc_ok = ResourceService(
            kinds=kinds, repo=repo, audit=audit, keyring=_FakeKeyring(present={"openai-key"})
        )
        await svc_ok.register(kind="knowledge_base", name="kb1", config=kb_config, actor="cli")
        await svc_ok.register(kind="memory", name="global", config=mem_config, actor="cli")

        # PATCH introducing a missing ref is rejected before the DB write too.
        bad_kb = {**kb_config, "embedding": {**kb_config["embedding"], "credential_ref": "nope"}}
        with pytest.raises(CredentialMissing):
            await svc_ok.update_config(
                ResourceRef("knowledge_base", "kb1"), new_config=bad_kb, actor="cli"
            )
        unchanged = await svc_ok.get(ResourceRef("knowledge_base", "kb1"))
        assert unchanged.config["embedding"]["credential_ref"] == "openai-key"
    finally:
        await engine.dispose()
