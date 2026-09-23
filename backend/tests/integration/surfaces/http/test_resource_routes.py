# backend/tests/integration/surfaces/http/test_resource_routes.py
import sqlite3

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Kind
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router


class _FakeConfig(BaseModel):
    foo: int
    bar: str = "default"


async def _client(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    kinds = {
        "fake_kind": Kind(
            name="fake_kind",
            display_name="Fake",
            config_schema=_FakeConfig,
        ),
        # A second kind only so a rename can be watched carrying a reach with
        # it — `fake_kind` declares none. Every kind may be renamed, so there
        # is no third kind here standing for the refusal there no longer is.
        "nameable": Kind(
            name="nameable",
            display_name="Nameable",
            config_schema=_FakeConfig,
            supports_scope=True,
        ),
    }
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    svc = ResourceService(kinds=kinds, repo=repo, audit=audit)

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(resource_router)
    app.dependency_overrides[get_resource_service] = lambda: svc

    set_active_token("test-token")
    transport = ASGITransport(app)
    client = AsyncClient(
        transport=transport, base_url="http://t", headers={"X-Coffer-Token": "test-token"}
    )
    return client, engine


@pytest.mark.asyncio
async def test_register_resource(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}, "description": "hi"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # The wire carries the identity, not a `<kind>:<name>` string built out
        # of two fields that are also on the object. ``uid`` is what every
        # other route takes; ``name`` is the label beside it.
        assert body["uid"]
        assert body["name"] == "t"
        assert body["kind"] == "fake_kind"
        assert body["config"] == {"foo": 1, "bar": "default"}
        assert body["enabled"] is True
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="reject an invalid registration and persist nothing",
)
async def test_register_duplicate_returns_409(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}},
        )
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 2}},
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS"
    await engine.dispose()


@pytest.mark.asyncio
async def test_generic_register_rejects_lifecycle_kind_returns_409(tmp_path):
    """CODE-REG: the generic POST /resources endpoint must refuse a kind that
    declares ``generic_create_allowed=False`` (skill/agent), so it can't create
    a row with no backing master folder / detected config dir."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    kinds = {
        "skill": Kind(
            name="skill",
            display_name="Skill",
            config_schema=_FakeConfig,
            generic_create_allowed=False,
        ),
    }
    svc = ResourceService(
        kinds=kinds,
        repo=SqlAlchemyResourceRepo(sm),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(resource_router)
    app.dependency_overrides[get_resource_service] = lambda: svc
    set_active_token("test-token")
    transport = ASGITransport(app)
    async with AsyncClient(
        transport=transport, base_url="http://t", headers={"X-Coffer-Token": "test-token"}
    ) as c:
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "skill", "name": "t", "config": {"foo": 1}},
        )
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "GENERIC_CREATE_NOT_ALLOWED"
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_unknown_kind_returns_400(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "nope", "name": "t", "config": {}},
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "UNKNOWN_KIND"
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="reject an invalid registration and persist nothing",
)
async def test_register_invalid_config_returns_422(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": "not_int"}},
        )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "CONFIG_INVALID"
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="the kind-agnostic surface serves every kind",
)
async def test_list_resources(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "a", "config": {"foo": 1}},
        )
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "b", "config": {"foo": 2}},
        )
        r = await c.get("/api/v1/resources")
        assert r.status_code == 200
        names = sorted(item["name"] for item in r.json()["resources"])
        assert names == ["a", "b"]
        # Filter by kind
        r = await c.get("/api/v1/resources?kind=fake_kind")
        assert r.status_code == 200
        assert len(r.json()["resources"]) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_filters_by_exact_name(tmp_path):
    """The ONE place a name may be used to find a resource.

    A surface that started from what a human typed — the CLI — turns it into
    the uid here, and then addresses the resource the way everything else does.
    It is a filter over the list rather than a lookup route precisely so it
    cannot be mistaken for an identity.
    """
    c, engine = await _client(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "a", "config": {"foo": 1}},
        )
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "b", "config": {"foo": 2}},
        )
        r = await c.get("/api/v1/resources?name=a")
        assert r.status_code == 200
        assert [item["uid"] for item in r.json()["resources"]] == [created.json()["uid"]]

        # Exact, not a prefix or a substring.
        assert (await c.get("/api/v1/resources?name=")).json()["resources"] == []
        assert (await c.get("/api/v1/resources?name=nope")).json()["resources"] == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_resource(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}},
        )
        uid = created.json()["uid"]
        r = await c.get(f"/api/v1/resources/{uid}")
        assert r.status_code == 200
        assert r.json()["name"] == "t"
        # Not found
        r = await c.get("/api/v1/resources/no-such-uid")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_resource_config(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}},
        )
        uid = created.json()["uid"]
        r = await c.patch(
            f"/api/v1/resources/{uid}",
            json={"config": {"foo": 99}, "description": "new desc"},
        )
        assert r.status_code == 200
        assert r.json()["config"]["foo"] == 99
        assert r.json()["description"] == "new desc"
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="renaming a resource is an ordinary edit",
)
async def test_patch_renames_any_kind(tmp_path):
    """Renaming is a FIELD on PATCH, not an operation, and it is available to
    every kind.

    While the name was the identity, moving it needed its own route — and only
    one kind of the seven ever got one, so for the other six "rename" meant
    delete-and-recreate, which threw away the audit trail and every reference.
    The uid is the identity now, so the label is just another editable field.
    """
    c, engine = await _client(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "before", "config": {"foo": 1}},
        )
        uid = created.json()["uid"]

        r = await c.patch(f"/api/v1/resources/{uid}", json={"name": "after"})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "after"
        # The identity did not move with the label, so the same URL still works.
        assert r.json()["uid"] == uid
        assert (await c.get(f"/api/v1/resources/{uid}")).json()["name"] == "after"
    await engine.dispose()


@pytest.mark.asyncio
async def test_patch_rename_onto_a_taken_label_returns_409(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        a = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "a", "config": {"foo": 1}},
        )
        await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "b", "config": {"foo": 2}},
        )
        r = await c.patch(f"/api/v1/resources/{a.json()['uid']}", json={"name": "b"})
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS"
        # Refused with nothing moved.
        assert (await c.get(f"/api/v1/resources/{a.json()['uid']}")).json()["name"] == "a"
    await engine.dispose()


@pytest.mark.asyncio
async def test_patch_rename_enforces_the_name_pattern(tmp_path):
    """The same rule registration applies. It used to be enforced wherever an
    identifier was BUILT, which is why the one kind that had a rename route
    checked something else entirely."""
    c, engine = await _client(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "ok", "config": {"foo": 1}},
        )
        r = await c.patch(f"/api/v1/resources/{created.json()['uid']}", json={"name": "bad name!"})
        assert r.status_code == 422, r.text
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="the kind-agnostic surface serves every kind",
)
async def test_enable_disable(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}},
        )
        uid = created.json()["uid"]
        r = await c.post(f"/api/v1/resources/{uid}/disable")
        assert r.status_code == 200
        assert r.json()["enabled"] is False
        r = await c.post(f"/api/v1/resources/{uid}/enable")
        assert r.status_code == 200
        assert r.json()["enabled"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_resource(tmp_path):
    c, engine = await _client(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 1}},
        )
        uid = created.json()["uid"]
        r = await c.delete(f"/api/v1/resources/{uid}")
        assert r.status_code == 204
        r = await c.get(f"/api/v1/resources/{uid}")
        assert r.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_resource_create_enforces_name_pattern(tmp_path):
    """D5: POST /api/v1/resources with an invalid name returns 422."""
    c, engine = await _client(tmp_path)
    async with c:
        r = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "bad name!", "config": {"foo": 1}},
        )
        assert r.status_code == 422, r.text
    await engine.dispose()


class _StubKeyring:
    """Minimal CredentialStorePort stand-in for register-time credential probing."""

    def __init__(self, store: dict[str, str] | None = None) -> None:
        self.store: dict[str, str] = dict(store or {})

    def get(self, ref: str) -> str | None:
        return self.store.get(ref)

    def set(self, ref: str, value: str) -> None:
        self.store[ref] = value

    def delete(self, ref: str) -> None:
        self.store.pop(ref, None)


async def _client_with_mcp_kind(tmp_path, keyring: _StubKeyring):
    """Like _client(), but registers the real `mcp_server` Kind so we can
    drive register-time credential probing against transport.credential_refs."""
    from coffer.application.mcp.kind import make_mcp_kind

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    # The production Kind wires the credential-ref extractor + audit redactor
    # (CODE-006) that drive probing/redaction; build it the real way.
    kinds = {"mcp_server": make_mcp_kind({})}
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    svc = ResourceService(kinds=kinds, repo=repo, audit=audit, credentials=keyring)

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(resource_router)
    app.dependency_overrides[get_resource_service] = lambda: svc

    set_active_token("test-token")
    transport = ASGITransport(app)
    client = AsyncClient(
        transport=transport, base_url="http://t", headers={"X-Coffer-Token": "test-token"}
    )
    return client, engine, repo


@pytest.mark.asyncio
async def test_register_with_missing_credential_returns_actionable_error(tmp_path):
    """Spec edge case: registering an MCP server whose transport.credential_refs
    cites a key absent from the keychain must fail BEFORE any DB write, name
    the missing ref in the error body, and leave the resources table unchanged.
    """
    keyring = _StubKeyring()  # empty — no credentials stored
    c, engine, repo = await _client_with_mcp_kind(tmp_path, keyring)
    async with c:
        before = await repo.list()
        before_count = len(before)
        r = await c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "remote",
                "config": {
                    "transport": {
                        "type": "http",
                        "url": "http://example.com/mcp",
                        "credential_refs": {"Authorization": "github.GITHUB_TOKEN"},
                    },
                },
            },
        )
        # 400 per the existing CREDENTIAL_MISSING -> HTTP mapping in errors.py.
        assert r.status_code == 400, r.text
        body = r.json()
        assert body["error"]["code"] == "CREDENTIAL_MISSING"
        # The missing ref must be named in the message so the user can act.
        assert "github.GITHUB_TOKEN" in body["error"]["message"]
        # No partial state — the resources table is unchanged.
        after = await repo.list()
        assert len(after) == before_count
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_with_present_credential_succeeds(tmp_path):
    """Counterpart: with the credential present in the keychain, registration
    proceeds normally."""
    keyring = _StubKeyring({"github.GITHUB_TOKEN": "ghp_xxx"})
    c, engine, _repo = await _client_with_mcp_kind(tmp_path, keyring)
    async with c:
        r = await c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "remote",
                "config": {
                    "transport": {
                        "type": "http",
                        "url": "http://example.com/mcp",
                        "credential_refs": {"Authorization": "github.GITHUB_TOKEN"},
                    },
                },
            },
        )
        assert r.status_code == 201, r.text
    await engine.dispose()


def _events(tmp_path, event_type: str) -> list[tuple[str, str]]:
    """Every audit entry of one type, as (kind, name-at-the-time)."""
    with sqlite3.connect(tmp_path / "c.db") as db:
        rows = db.execute(
            "SELECT resource_kind, resource_name FROM audit_log WHERE event_type = ? ORDER BY id",
            (event_type,),
        ).fetchall()
    return [(kind, name) for kind, name in rows]


def _renames(tmp_path) -> list[tuple[str, str]]:
    """Every `resource_renamed` entry, as (kind, name-at-the-time)."""
    with sqlite3.connect(tmp_path / "c.db") as db:
        rows = db.execute(
            "SELECT resource_kind, resource_name FROM audit_log "
            "WHERE event_type = 'resource_renamed' ORDER BY id"
        ).fetchall()
    return [(kind, name) for kind, name in rows]


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="renaming a resource is an ordinary edit",
)
async def test_a_rename_carries_everything_that_was_not_the_name(tmp_path):
    """The name is a label, so it moves and nothing else does.

    See "Treat a resource's name as a mutable label".
    """
    c, engine = await _client(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={"kind": "nameable", "name": "draft", "config": {"foo": 1}, "description": "hi"},
        )
        uid = created.json()["uid"]
        await c.put(f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": ["a"]}})
        await c.post(f"/api/v1/resources/{uid}/disable")

        r = await c.patch(f"/api/v1/resources/{uid}", json={"name": "release"})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "release"

        # Everything that was not the name came with it — and it is reachable
        # at the address it always had, which is the change made visible.
        moved = (await c.get(f"/api/v1/resources/{uid}")).json()
        assert moved["config"] == {"foo": 1, "bar": "default"}
        assert moved["description"] == "hi"
        assert moved["enabled"] is False
        assert moved["scope"] == {"agents": ["a"]}

        # The trail is against the ROW, which never moved. Read straight out
        # of the table: this app mounts the resource router only.
        assert _renames(tmp_path) == [("nameable", "release")]

        # A name already taken.
        await c.post(
            "/api/v1/resources",
            json={"kind": "nameable", "name": "taken", "config": {"foo": 2}},
        )
        clash = await c.patch(f"/api/v1/resources/{uid}", json={"name": "taken"})
        assert clash.status_code == 409
        assert clash.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS"

        # The name it already has is a no-op, not a second audit entry.
        same = await c.patch(f"/api/v1/resources/{uid}", json={"name": "release"})
        assert same.status_code == 200
        assert len(_renames(tmp_path)) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_rename_alone_does_not_rewrite_the_config(tmp_path):
    """A PATCH carrying only a name touches only the name.

    Writing the stored config back over itself is not a no-op — it re-validates,
    re-probes every credential the config cites, fires the kind's update hook
    and records a `resource_updated` whose before and after are identical. A
    rename refused because of something the caller never touched is the failure
    this guards.
    """
    c, engine = await _client(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={"kind": "nameable", "name": "draft", "config": {"foo": 1}},
        )
        before = len(_events(tmp_path, "resource_updated"))

        r = await c.patch(f"/api/v1/resources/{created.json()['uid']}", json={"name": "release"})

        assert r.status_code == 200, r.text
        assert len(_events(tmp_path, "resource_updated")) == before
        assert _renames(tmp_path) == [("nameable", "release")]
    await engine.dispose()


@pytest.mark.asyncio
async def test_an_explicit_null_config_leaves_the_stored_one_alone(tmp_path):
    """A client that fills in a field it has no value for has said nothing
    about the config — not that the config should be emptied. One that wants it
    empty says `{}`."""
    c, engine = await _client(tmp_path)
    async with c:
        created = await c.post(
            "/api/v1/resources",
            json={"kind": "fake_kind", "name": "t", "config": {"foo": 7, "bar": "keep"}},
        )

        r = await c.patch(
            f"/api/v1/resources/{created.json()['uid']}",
            json={"config": None, "description": "only the words changed"},
        )

        assert r.status_code == 200, r.text
        assert r.json()["config"] == {"foo": 7, "bar": "keep"}
        assert r.json()["description"] == "only the words changed"
    await engine.dispose()
