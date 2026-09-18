"""Renaming an `mcp_server` or a `channel` does not disturb its secrets.

``test_resource_rename.py`` proves this for the framework with a synthetic kind.
This file proves it for the two kinds that used to mint a credential ref out of
the resource's NAME — ``channel/<name>/<secret>`` and ``<name>.<env key>`` —
using their REAL ``Kind`` definitions and their real config schemas, because the
name-derived ref was never a framework fact: it was two front-end files spelling
an address, and the only reason it was survivable was that neither kind could be
renamed at all.

What is asserted after each rename is a round trip, not a string: the config
still cites a ref, that ref is still in the store, and the value that comes back
is the one that went in. A ref rewritten without its stored row, or a row moved
without its citation, passes any test that only looks at one of the three.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.channel.kind import make_channel_kind
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.resource_kind_ops import credential_refs
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

MACHINE = "machine-under-test"

#: Refs in the shape `lib/credentialRef.ts` now mints — opaque body, readable
#: tail. Written out as literals rather than generated, so the test states the
#: shape it is defending instead of agreeing with whatever the code produced.
BOT_TOKEN_REF = "channel/2f0d3a1b4c5e6f708192a3b4c5d6e7f8/bot-token"
ENV_KEY_REF = "mcp_server/8e7d6c5b4a39281706f5e4d3c2b1a099/SMART_PAT"


class _AgentConfig(BaseModel):
    """Enough of an `agent` for a channel to bind to. The real kind is not
    imported because none of what it adds is read here: the channel kind asks
    the resource table for ``{uid: name}`` and nothing else."""

    type: str = "claude_code"


class _Store:
    """The smallest credential store ``ResourceService`` will talk to."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self.values.get(ref)

    def exists(self, ref: str) -> bool:
        return ref in self.values

    def delete(self, ref: str) -> None:
        self.values.pop(ref, None)


async def _service(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'refs.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    repo = SqlAlchemyResourceRepo(sm)

    async def agent_names() -> dict[str, str]:
        return {r.uid: r.name for r in await repo.list() if r.kind == "agent"}

    kinds: dict[str, Kind] = {
        "agent": Kind(name="agent", display_name="Agent", config_schema=_AgentConfig),
        "mcp_server": make_mcp_kind({}),
        "channel": make_channel_kind(agent_names=agent_names, local_machine_id=MACHINE),
    }
    store = _Store()
    store.values[BOT_TOKEN_REF] = "telegram-bot-token"
    store.values[ENV_KEY_REF] = "smart-personal-access-token"
    svc = ResourceService(
        kinds=kinds,
        repo=repo,
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
        credentials=store,
    )
    return svc, store, engine


async def _resolves(svc: ResourceService, store: _Store, uid: str) -> dict[str, str]:
    """``{logical key: secret value}`` reached the way the runtime reaches it —
    through the kind's own extractor and then the store, never by string."""
    resource = await svc.get(uid)
    kind_def = svc._kinds[resource.kind]
    refs = credential_refs(kind_def, resource.config)
    return {key: store.get(ref) for key, ref in refs.items() if store.get(ref) is not None}


async def test_renaming_an_mcp_server_keeps_its_secret_reachable(tmp_path):
    svc, store, engine = await _service(tmp_path)
    try:
        created = await svc.register(
            kind="mcp_server",
            name="smart",
            config={
                "transport": {
                    "type": "http",
                    "url": "https://example.invalid/mcp",
                    "credential_refs": {"SMART_PAT": ENV_KEY_REF},
                }
            },
            actor="test",
        )
        assert await _resolves(svc, store, created.uid) == {
            "SMART_PAT": "smart-personal-access-token"
        }

        await svc.rename(created.uid, "shopee-smart", actor="test")

        renamed = await svc.get(created.uid)
        assert renamed.name == "shopee-smart"
        # The citation did not move, the stored row did not move, and the value
        # still comes back.
        assert renamed.config["transport"]["credential_refs"]["SMART_PAT"] == ENV_KEY_REF
        assert await _resolves(svc, store, created.uid) == {
            "SMART_PAT": "smart-personal-access-token"
        }
        # And nothing about either name was ever in the address.
        assert "smart" not in ENV_KEY_REF.split("/")[1]
    finally:
        await engine.dispose()


async def test_renaming_a_channel_keeps_its_secret_reachable(tmp_path):
    svc, store, engine = await _service(tmp_path)
    try:
        agent = await svc.register(kind="agent", name="claude-code", config={}, actor="test")
        created = await svc.register(
            kind="channel",
            name="tg",
            config={
                "channel_type": "telegram",
                "bot_token_ref": BOT_TOKEN_REF,
                "default_agent": agent.uid,
                "runs_on": MACHINE,
            },
            actor="test",
        )
        assert await _resolves(svc, store, created.uid) == {"bot_token_ref": "telegram-bot-token"}

        await svc.rename(created.uid, "telegram-personal", actor="test")

        renamed = await svc.get(created.uid)
        assert renamed.name == "telegram-personal"
        assert renamed.config["bot_token_ref"] == BOT_TOKEN_REF
        assert await _resolves(svc, store, created.uid) == {"bot_token_ref": "telegram-bot-token"}
        assert "tg" not in BOT_TOKEN_REF.split("/")[1]
    finally:
        await engine.dispose()


async def test_deleting_a_renamed_server_releases_only_its_own_secret(tmp_path):
    """The hazard the opaque ref closes, stated as behaviour.

    ``release_orphaned_credentials`` decides ownership by CITATION. With one
    address per secret that is exactly right — and it stays right across a
    rename, which is what a name-derived ref could not promise: the deleted row
    and the surviving one would have been arguing about which of them the string
    ``smart.SMART_PAT`` described.
    """
    svc, store, engine = await _service(tmp_path)
    try:
        shared = "mcp_server/1111111111111111111111111111aaaa/SHARED"
        store.values[shared] = "shared-between-two-servers"
        one = await svc.register(
            kind="mcp_server",
            name="one",
            config={
                "transport": {
                    "type": "http",
                    "url": "https://example.invalid/a",
                    "credential_refs": {"SMART_PAT": ENV_KEY_REF, "SHARED": shared},
                }
            },
            actor="test",
        )
        await svc.register(
            kind="mcp_server",
            name="two",
            config={
                "transport": {
                    "type": "http",
                    "url": "https://example.invalid/b",
                    "credential_refs": {"SHARED": shared},
                }
            },
            actor="test",
        )
        await svc.rename(one.uid, "one-renamed", actor="test")
        await svc.delete(one.uid, actor="test")

        # Its own secret went; the one the other server still cites stayed.
        assert ENV_KEY_REF not in store.values
        assert store.values[shared] == "shared-between-two-servers"
    finally:
        await engine.dispose()


@pytest.mark.parametrize("ref", [BOT_TOKEN_REF, ENV_KEY_REF])
def test_the_minted_shape_is_a_legal_credential_ref(ref):
    """The API's own pattern for a ref — three slash-separated segments of the
    allowed alphabet. A shape the store would refuse would fail only at the
    moment a user saves a secret."""
    from coffer.surfaces.http.schemas import CredentialSetIn

    assert CredentialSetIn(ref=ref, value="x").ref == ref
