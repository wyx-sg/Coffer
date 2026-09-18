import pytest
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.service import KIND_KNOWLEDGE
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    ConfigValidationError,
    ResourceAlreadyExists,
    ResourceNotFound,
    UnknownKind,
)
from coffer.domain.resource import Kind, Resource
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
    # register MINTS the identity, and it is not derived from anything the user
    # can change: two resources with the same name in different kinds, or one
    # renamed later, never collide here.
    assert r.uid
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
async def test_register_mints_a_distinct_uid_per_resource(tmp_path):
    svc, _, engine = await _service(tmp_path)
    a = await svc.register(kind="fake_kind", name="a", config={"foo": 1}, actor="cli")
    b = await svc.register(kind="fake_kind", name="b", config={"foo": 1}, actor="cli")
    assert a.uid != b.uid
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_accepts_a_supplied_uid_for_the_sync_applier(tmp_path):
    """``uid=`` has exactly one caller: the sync applier, putting a resource
    this vault has not seen before at the identity the other machine already
    gave it. Without that, the same resource on two machines would be two
    resources and every reference to it would resolve on only one of them."""
    svc, _, engine = await _service(tmp_path)
    r = await svc.register(
        kind="fake_kind", name="t", config={"foo": 1}, actor="sync", uid="from-the-other-machine"
    )
    assert r.uid == "from-the-other-machine"
    assert (await svc.get("from-the-other-machine")).name == "t"
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
            await svc.update_config(r.uid, new_config={"foo": 2}, actor="cli")
        updated = await svc.update_config(
            r.uid,
            new_config={"foo": 2},
            actor="skill-service",
            allow_lifecycle_kind=True,
        )
        assert updated.config["foo"] == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_kind_supplied_credential_extractor_and_audit_redactor(tmp_path):
    """CODE-006 / resource framework: ResourceService must NOT hardcode the mcp_server
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
async def test_find_credential_citations_lists_referencing_resources(tmp_path):
    """find_credential_citations scans every resource's config (via each kind's
    credential_ref_extractor) and returns the RESOURCES that cite a given
    credential — so the credential-delete route can refuse and name them back
    to the user. A credential nothing references yields an empty list; kinds
    without an extractor are skipped, not crashed.

    It returns whole resources rather than identifiers because both callers
    want more than the identity: the 409 names the citing resources, and the
    orphan-release check only asks whether the list is empty.
    """

    class _SecretConfig(BaseModel):
        secret_ref: str

    class _PlainConfig(BaseModel):
        foo: int = 0

    class _FakeKeyring:
        def get(self, ref: str) -> str | None:
            return "value"  # every probed ref is present

    kinds = {
        "vault": Kind(
            name="vault",
            display_name="Vault",
            config_schema=_SecretConfig,
            credential_ref_extractor=lambda cfg: {"secret": cfg["secret_ref"]},
        ),
        "plain": Kind(
            name="plain",
            display_name="Plain",
            config_schema=_PlainConfig,
        ),
    }

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'cite.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    try:
        svc = ResourceService(
            kinds=kinds,
            repo=SqlAlchemyResourceRepo(sm),
            audit=audit,
            credentials=_FakeKeyring(),
        )
        a = await svc.register(kind="vault", name="a", config={"secret_ref": "k1"}, actor="cli")
        b = await svc.register(kind="vault", name="b", config={"secret_ref": "k1"}, actor="cli")
        await svc.register(kind="vault", name="c", config={"secret_ref": "k2"}, actor="cli")
        # An extractor-less kind must be skipped, not crash the scan.
        await svc.register(kind="plain", name="d", config={"foo": 1}, actor="cli")

        citing_k1 = await svc.find_credential_citations("k1")
        assert all(isinstance(r, Resource) for r in citing_k1)
        # Identified by uid — the list is a set of resources, not of labels.
        assert sorted(r.uid for r in citing_k1) == sorted([a.uid, b.uid])
        # And it carries the labels the 409 message shows the user.
        assert sorted(r.name for r in citing_k1) == ["a", "b"]

        # A credential nothing references → empty list (delete proceeds).
        assert await svc.find_credential_citations("unused") == []
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
    """The NAME is still unique within a kind — it is a label a user reads, and
    two skills called the same thing help nobody. Uniqueness is a constraint on
    the label; it stopped being the identity."""
    svc, _, engine = await _service(tmp_path)
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    with pytest.raises(ResourceAlreadyExists):
        await svc.register(kind="fake_kind", name="t", config={"foo": 2}, actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_and_get(tmp_path):
    svc, _, engine = await _service(tmp_path)
    a = await svc.register(kind="fake_kind", name="a", config={"foo": 1}, actor="cli")
    await svc.register(kind="fake_kind", name="b", config={"foo": 2}, actor="cli")

    all_resources = await svc.list()
    assert {r.name for r in all_resources} == {"a", "b"}

    r = await svc.get(a.uid)
    assert r.config == {"foo": 1, "bar": "default"}

    with pytest.raises(ResourceNotFound):
        await svc.get("no-such-uid")
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_by_name_is_the_label_path(tmp_path):
    """The one resolution that starts from what a human typed. It reports the
    LABEL back when nothing answers, because a lookup that began with a name
    and failed with a uid in the message would help nobody."""
    svc, _, engine = await _service(tmp_path)
    created = await svc.register(kind="fake_kind", name="a", config={"foo": 1}, actor="cli")

    assert (await svc.get_by_name("fake_kind", "a")).uid == created.uid
    assert await svc.find_by_name("fake_kind", "nope") is None

    with pytest.raises(ResourceNotFound, match="no fake_kind named 'nope'"):
        await svc.get_by_name("fake_kind", "nope")
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_config_audits_with_before_after(tmp_path):
    svc, audit, engine = await _service(tmp_path)
    created = await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    await svc.update_config(
        created.uid,
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
    created = await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")

    # idempotent: enabling an already-enabled resource doesn't audit
    await svc.set_enabled(created.uid, True, actor="api")
    enabled_events = await audit.query(event_type=AuditEventType.RESOURCE_ENABLED.value)
    assert len(enabled_events) == 0

    await svc.set_enabled(created.uid, False, actor="api")
    disabled_events = await audit.query(event_type=AuditEventType.RESOURCE_DISABLED.value)
    assert len(disabled_events) == 1
    assert disabled_events[0].actor == "api"
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_invokes_on_delete_hook_and_audits(tmp_path):
    calls: list[Resource] = []
    svc, audit, engine = await _service(tmp_path, on_delete=lambda resource: calls.append(resource))
    created = await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    await svc.delete(created.uid, actor="cli")
    # The hook is handed the row it is cleaning up after, so it has the kind,
    # the label AND the identity without a lookup that could come back empty.
    assert [(r.uid, r.kind, r.name) for r in calls] == [(created.uid, "fake_kind", "t")]
    assert await svc.list() == []

    entries = await audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert len(entries) == 1
    assert entries[0].details.get("snapshot") is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_aborts_when_on_delete_raises(tmp_path):
    def boom(resource: Resource) -> None:
        raise RuntimeError("cleanup failed")

    svc, audit, engine = await _service(tmp_path, on_delete=boom)
    created = await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await svc.delete(created.uid, actor="cli")

    # Resource still exists
    r = await svc.get(created.uid)
    assert r.name == "t"
    # No deletion audit entry
    entries = await audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert entries == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_unknown_resource_raises(tmp_path):
    svc, _, engine = await _service(tmp_path)
    with pytest.raises(ResourceNotFound):
        await svc.delete("no-such-uid", actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_knowledge_kind_declares_no_credentials(tmp_path):
    """The knowledge kind supplies no credential extractor, so registering a
    collection never probes the keychain.

    Both former faces used to extract an embedding API-key ref from their own
    config. Nothing about a directory of files needs a credential, so there is
    none to probe — and a register must not fail on a keychain that holds
    nothing."""
    from coffer.application.knowledge.kind import make_knowledge_kind

    class _EmptyKeyring:
        def get(self, ref: str) -> str | None:
            return None

    # The kind's hooks never touch the wrapped service at register time.
    kind = make_knowledge_kind(None)  # type: ignore[arg-type]
    assert kind.credential_ref_extractor is None

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    try:
        svc = ResourceService(
            kinds={KIND_KNOWLEDGE: kind},
            repo=SqlAlchemyResourceRepo(sm),
            audit=audit,
            credentials=_EmptyKeyring(),
        )
        created = await svc.register(
            kind=KIND_KNOWLEDGE,
            name="shopee",
            config={},
            actor="cli",
            allow_lifecycle_kind=True,
        )
        stored = await svc.get(created.uid)
        # A collection carries no config at all (spec knowledge FR-046).
        assert stored.config == {}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="credentials",
    scenario="deleting a resource releases the credentials nothing else cites",
)
async def test_delete_releases_credentials_only_it_cited(tmp_path):
    """Deleting a resource drops the credentials nothing else cites; a ref
    still cited by another resource survives (2026-07-10 orphan incident)."""

    class _SecretConfig(BaseModel):
        secret_ref: str

    class _FakeStore:
        def __init__(self, present: set[str]) -> None:
            self.store = dict.fromkeys(present, "value")

        def get(self, ref: str) -> str | None:
            return self.store.get(ref)

        def exists(self, ref: str) -> bool:
            return ref in self.store

        def delete(self, ref: str) -> None:
            self.store.pop(ref, None)

    kinds = {
        "vault": Kind(
            name="vault",
            display_name="Vault",
            config_schema=_SecretConfig,
            credential_ref_extractor=lambda cfg: {"secret": cfg["secret_ref"]},
        ),
    }
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    store = _FakeStore(present={"only-mine", "shared"})
    svc = ResourceService(
        kinds=kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit, credentials=store
    )
    try:
        a = await svc.register("vault", "a", {"secret_ref": "only-mine"}, "t")
        b = await svc.register("vault", "b", {"secret_ref": "shared"}, "t")
        c = await svc.register("vault", "c", {"secret_ref": "shared"}, "t")

        await svc.delete(a.uid, "t")
        assert not store.exists("only-mine")  # released with its only citer

        await svc.delete(b.uid, "t")
        assert store.exists("shared")  # still cited by c

        await svc.delete(c.uid, "t")
        assert not store.exists("shared")  # last citation gone

        entries = await audit.query(event_type=AuditEventType.CREDENTIAL_DELETED.value)
        assert {e.details["ref"] for e in entries} == {"only-mine", "shared"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_without_credential_store_is_unaffected(tmp_path):
    class _SecretConfig(BaseModel):
        secret_ref: str

    kinds = {
        "vault": Kind(
            name="vault",
            display_name="Vault",
            config_schema=_SecretConfig,
            credential_ref_extractor=lambda cfg: {"secret": cfg["secret_ref"]},
        ),
    }
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    svc = ResourceService(
        kinds=kinds,
        repo=SqlAlchemyResourceRepo(sm),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    try:
        a = await svc.register("vault", "a", {"secret_ref": "unprobed"}, "t")
        await svc.delete(a.uid, "t")  # must not raise
        with pytest.raises(ResourceNotFound):
            await svc.get(a.uid)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_register_probes_credentials_off_the_loop_thread(tmp_path) -> None:
    """The credential store's ``get`` is a blocking SQLite read; the register-time
    probe must run it in a worker thread, not on the loop it would stall."""
    import threading

    class _SecretConfig(BaseModel):
        secret_ref: str

    loop_thread = threading.get_ident()
    seen: list[int] = []

    class _RecordingStore:
        def get(self, ref: str) -> str | None:
            seen.append(threading.get_ident())
            return "value"

    kinds = {
        "vault": Kind(
            name="vault",
            display_name="Vault",
            config_schema=_SecretConfig,
            credential_ref_extractor=lambda cfg: {"secret": cfg["secret_ref"]},
        ),
    }
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    try:
        svc = ResourceService(
            kinds=kinds,
            repo=SqlAlchemyResourceRepo(sm),
            audit=AuditService(SqlAlchemyAuditRepo(sm)),
            credentials=_RecordingStore(),
        )
        created = await svc.register(
            kind="vault", name="t", config={"secret_ref": "k1"}, actor="cli"
        )
        await svc.update_config(created.uid, {"secret_ref": "k2"}, actor="cli")
    finally:
        await engine.dispose()
    assert len(seen) == 2, "register and update each probe once"
    assert all(ident != loop_thread for ident in seen)
