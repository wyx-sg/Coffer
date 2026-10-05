"""``/api/v1/vault`` — the history of a vault file or folder, a version's
diff, restoring a version, and the hand edits the vault kept out
(coffer.surfaces.http.vault_routes; spec vault-storage "Show and restore any
version of a vault file or folder", "List the hand edits the vault kept out").

The router runs alone over the vault writer, with the audit recorder and the
actor overridden; every test runs in its own HOME (tests/conftest.py).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.domain.vault.writers import WRITER_AGENT, WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_repository, vault_writer
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.vault_routes import router as vault_router

TOKEN = "t-vault-routes"
USER = CommitMeta(writer=WRITER_USER, operation="edit", summary="Saved", actor="ui")
AGENT = CommitMeta(
    writer=WRITER_AGENT, operation="edit", summary="Edited", actor="agent", agent="claude-code"
)


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    async def record(
        self, event_type: str, *, actor: str = "system", details: dict[str, Any] | None = None
    ) -> None:
        self.events.append((event_type, actor, details or {}))


@pytest.fixture
def audit() -> _Audit:
    return _Audit()


@pytest.fixture
def client(audit: _Audit) -> AsyncClient:
    set_active_token(TOKEN)
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(vault_router)
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_actor] = lambda: "ui"
    return AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
    )


def _write(
    path: str, data: bytes, expected: str | Expect = Expect.HEAD, meta: CommitMeta = USER
) -> str:
    version = vault_writer().write_file(path, data, meta=meta, expected=expected)
    assert version is not None
    return version


@pytest.mark.acceptance(
    spec="vault-storage", scenario="a file's history lists its versions with their writers"
)
async def test_a_files_history_lists_its_versions_with_their_writers(client: AsyncClient) -> None:
    path = "knowledge/notes/cache.md"
    _write(path, b"one\n", Expect.ABSENT)
    _write(path, b"one\ntwo\n", meta=AGENT)
    # An edit in the person's own editor, not yet committed: the read commits
    # it first, as a version of its own.
    (vault_root() / path).write_bytes(b"one\ntwo\nthree\n")
    async with client:
        r = await client.get("/api/v1/vault/history", params={"path": path})
    assert r.status_code == 200, r.text
    versions = r.json()["versions"]
    assert [v["display_writer"] for v in versions] == ["disk", "agent:claude-code", "user"]
    assert [[(p["path"], p["status"]) for p in v["paths"]] for v in versions] == [
        [(path, "modified")],
        [(path, "modified")],
        [(path, "added")],
    ]
    assert versions[0]["paths"][0]["added"] == 1
    assert r.json()["next_cursor"] is None


@pytest.mark.acceptance(
    spec="vault-storage", scenario="a version's diff reads against the one before it or the current"
)
async def test_a_versions_diff_reads_against_the_one_before_it_or_the_current(
    client: AsyncClient,
) -> None:
    first = _write("skills/pdf/SKILL.md", b"v1\n", Expect.ABSENT)
    second = _write("skills/pdf/SKILL.md", b"v2\n")
    _write("skills/pdf/extra.md", b"later\n", Expect.ABSENT)
    async with client:
        own = await client.get(
            "/api/v1/vault/diff", params={"path": "skills/pdf/", "version": second}
        )
        now = await client.get(
            "/api/v1/vault/diff",
            params={"path": "skills/pdf/", "version": first, "against": "current"},
        )
        not_a_version = await client.get(
            "/api/v1/vault/diff", params={"path": "skills/pdf/", "version": "HEAD~1"}
        )
        untouched = await client.get(
            "/api/v1/vault/diff", params={"path": "knowledge/a.md", "version": second}
        )
    assert own.status_code == 200, own.text
    (only,) = own.json()["files"]
    assert only["path"] == "skills/pdf/SKILL.md" and only["status"] == "modified"
    assert "-v1" in only["diff"] and "+v2" in only["diff"]
    assert now.json()["against"] == "current"
    files = {f["path"]: f for f in now.json()["files"]}
    assert files["skills/pdf/SKILL.md"]["status"] == "modified"
    assert (files["skills/pdf/SKILL.md"]["added"], files["skills/pdf/SKILL.md"]["removed"]) == (
        1,
        1,
    )
    assert files["skills/pdf/extra.md"]["status"] == "added"
    assert not_a_version.status_code == 404
    assert untouched.status_code == 404
    assert untouched.json()["error"]["code"] == "VAULT_VERSION_NOT_FOUND"


@pytest.mark.acceptance(
    spec="vault-storage", scenario="restore is a new commit through the same checks"
)
async def test_restore_is_a_new_commit_through_the_same_checks(
    client: AsyncClient, audit: _Audit
) -> None:
    path = "knowledge/a.md"
    first = _write(path, b"one\n", Expect.ABSENT)
    second = _write(path, b"two\n")
    async with client:
        stale = await client.post(
            "/api/v1/vault/restore",
            json={"path": path, "version": first, "expected_current": first},
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error"]["code"] == "VAULT_FILE_STALE"
        assert vault_repository().head() == second
        good = await client.post(
            "/api/v1/vault/restore",
            json={"path": path, "version": first, "expected_current": second},
        )
        assert good.status_code == 200, good.text
        again = await client.get("/api/v1/vault/history", params={"path": path})
    body = good.json()
    assert body["restored_from"] == first and body["paths"] == [path]
    head = vault_repository().log(limit=1)[0]
    assert head.version == body["version"] and head.meta.restored_from == first
    assert head.meta.writer == WRITER_USER
    assert (vault_root() / path).read_bytes() == b"one\n"
    # History was added to, never rewritten.
    assert [v["version"] for v in again.json()["versions"]] == [body["version"], second, first]
    assert again.json()["versions"][0]["restored_from"] == first
    assert [(e[0], e[1]) for e in audit.events] == [("vault_file_restored", "ui")]
    assert audit.events[0][2]["restored_from"] == first


async def test_a_restore_is_refused_after_an_edit_on_disk(client: AsyncClient) -> None:
    path = "knowledge/a.md"
    first = _write(path, b"one\n", Expect.ABSENT)
    second = _write(path, b"two\n")
    (vault_root() / path).write_bytes(b"edited in my editor\n")
    async with client:
        r = await client.post(
            "/api/v1/vault/restore",
            json={"path": path, "version": first, "expected_current": second},
        )
    assert r.status_code == 409, r.text
    assert (vault_root() / path).read_bytes() == b"edited in my editor\n"


@pytest.mark.acceptance(
    spec="vault-storage", scenario="restoring a folder removes files the version did not have"
)
async def test_restoring_a_folder_removes_files_the_version_did_not_have(
    client: AsyncClient, audit: _Audit
) -> None:
    first = _write("skills/pdf/SKILL.md", b"v1\n", Expect.ABSENT)
    _write("skills/pdf/SKILL.md", b"v2\n")
    _write("skills/pdf/extra.md", b"later\n", Expect.ABSENT)
    async with client:
        history = await client.get("/api/v1/vault/history", params={"path": "skills/pdf/"})
        versions = history.json()["versions"]
        assert [len(v["paths"]) for v in versions] == [1, 1, 1]
        r = await client.post(
            "/api/v1/vault/restore",
            json={
                "path": "skills/pdf/",
                "version": first,
                "expected_current": versions[0]["version"],
            },
        )
    assert r.status_code == 200, r.text
    assert sorted(r.json()["paths"]) == ["skills/pdf/SKILL.md", "skills/pdf/extra.md"]
    assert sorted(vault_repository().tree("HEAD", "skills/pdf/")) == ["skills/pdf/SKILL.md"]
    assert not (vault_root() / "skills/pdf/extra.md").exists()
    assert [e[0] for e in audit.events] == ["vault_file_restored"]


@pytest.mark.acceptance(
    spec="vault-storage", scenario="a secret's history is never read or restored"
)
async def test_a_secrets_history_is_never_read_or_restored(client: AsyncClient) -> None:
    first = _write("knowledge/a.md", b"one\n", Expect.ABSENT)
    async with client:
        refused = [
            await client.get("/api/v1/vault/history", params={"path": "secret/github.enc"}),
            await client.get("/api/v1/vault/history", params={"path": "secret/"}),
            await client.get("/api/v1/vault/history", params={"path": "../etc/passwd"}),
            await client.get(
                "/api/v1/vault/diff", params={"path": "secret/x.enc", "version": first}
            ),
            await client.post(
                "/api/v1/vault/restore", json={"path": "secret/x.enc", "version": first}
            ),
        ]
    for r in refused:
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "VAULT_PATH_INVALID"


async def test_the_routes_need_the_token(client: AsyncClient) -> None:
    bad = {"X-Coffer-Token": "not-the-token"}
    async with client:
        problems = await client.get("/api/v1/vault/problems", headers=bad)
        history = await client.get(
            "/api/v1/vault/history", params={"path": "knowledge/a.md"}, headers=bad
        )
    assert problems.status_code == 401
    assert history.status_code == 401
