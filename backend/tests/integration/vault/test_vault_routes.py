"""``/api/v1/vault`` — the restore hand-off and the hand edits the vault kept
out (coffer.surfaces.http.vault_routes; spec vault-storage "Hand restoring an
earlier version of a vault file to an agent", "List the hand edits the vault
kept out").

The vault's history is git's: the router lists, diffs and restores no version,
and the hand-off route writes nothing. The router runs alone over the vault
writer; every test runs in its own HOME (tests/conftest.py).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.domain.vault.writers import (
    OP_RESTORE,
    WRITER_AGENT,
    WRITER_USER,
    CommitMeta,
    message,
)
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.vault import git
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_repository, vault_writer
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.vault_routes import router as vault_router

TOKEN = "t-vault-routes"
USER = CommitMeta(writer=WRITER_USER, operation="edit", summary="Saved", actor="ui")


@pytest.fixture
def client() -> AsyncClient:
    set_active_token(TOKEN)
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(vault_router)
    return AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
    )


def _write(path: str, data: bytes, expected: str | Expect = Expect.HEAD) -> str:
    version = vault_writer().write_file(path, data, meta=USER, expected=expected)
    assert version is not None
    return version


@pytest.mark.acceptance(
    spec="vault-storage",
    scenario="the restore hand-off names the file, the time and the commit rules",
)
async def test_the_restore_hand_off_names_the_file_the_time_and_the_commit_rules(
    client: AsyncClient,
) -> None:
    _write("knowledge/shopee/cache.md", b"one\n", Expect.ABSENT)
    head = vault_repository().head()
    async with client:
        timed = await client.post(
            "/api/v1/vault/history/handoff",
            json={"path": "knowledge/shopee/cache.md", "at": "2026-09-01T10:30:00Z"},
        )
        untimed = await client.post(
            "/api/v1/vault/history/handoff", json={"path": "knowledge/shopee/cache.md"}
        )
        folder = await client.post(
            "/api/v1/vault/history/handoff", json={"path": "knowledge/shopee/"}
        )
    assert timed.status_code == 200, timed.text
    vault = str(vault_root())
    body = timed.json()
    assert body["path"] == "knowledge/shopee/cache.md"
    assert body["absolute_path"] == f"{vault}/knowledge/shopee/cache.md"
    assert body["vault_path"] == vault
    assert body["log_command"] == f"git -C {vault} log -p -- knowledge/shopee/cache.md"
    prompt = body["handoff"]["prompt"]
    assert "knowledge/shopee/cache.md" in prompt
    assert "2026-09-01T10:30:00+00:00" in prompt
    assert f"git repository at {vault}" in prompt
    for rule in ("reset", "amend", "rebase", "force push"):
        assert rule in prompt
    for trailer in (
        "Coffer-Writer: agent",
        "Coffer-Operation: restore",
        "Coffer-Restored-From:",
    ):
        assert trailer in prompt
    assert "touching only knowledge/shopee/cache.md" in prompt
    # Asked without a time, the agent lists the versions and asks which one.
    assert untimed.status_code == 200, untimed.text
    assert "list the file's recent versions" in untimed.json()["handoff"]["prompt"].lower()
    assert "2026" not in untimed.json()["handoff"]["prompt"]
    # A folder also has the files its version did not have removed.
    assert folder.json()["log_command"].endswith("log -p -- knowledge/shopee")
    assert (
        "remove the files inside it that version did not have" in folder.json()["handoff"]["prompt"]
    )
    # The route writes nothing.
    assert vault_repository().head() == head


async def test_a_path_with_a_space_is_quoted_in_the_git_command(client: AsyncClient) -> None:
    async with client:
        r = await client.post(
            "/api/v1/vault/history/handoff", json={"path": "knowledge/my notes/a b.md"}
        )
    assert r.status_code == 200, r.text
    assert r.json()["log_command"].endswith("log -p -- 'knowledge/my notes/a b.md'")


@pytest.mark.acceptance(spec="vault-storage", scenario="a secret's history is never handed over")
async def test_a_secrets_history_is_never_handed_over(client: AsyncClient) -> None:
    async with client:
        refused = [
            await client.post("/api/v1/vault/history/handoff", json={"path": path})
            for path in ("secret/github.enc", "secret/", "../etc/passwd", "/etc/passwd")
        ]
    for r in refused:
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "VAULT_PATH_INVALID"
        assert "handoff" not in r.json()


@pytest.mark.acceptance(
    spec="vault-storage",
    scenario="a version written back and committed outside Coffer is a new commit",
)
def test_a_version_written_back_and_committed_outside_coffer_is_a_new_commit() -> None:
    first = _write("knowledge/a.md", b"one\n", Expect.ABSENT)
    second = _write("knowledge/a.md", b"two\n")
    root = vault_root()

    # What the agent does with the hand-off's prompt: write the first version's
    # bytes back, and commit them with the three trailers.
    (root / "knowledge" / "a.md").write_bytes(
        git.text(git.run(root, "show", f"{first}:knowledge/a.md")).encode()
    )
    trailers = CommitMeta(
        writer=WRITER_AGENT,
        operation=OP_RESTORE,
        summary="Restore knowledge/a.md",
        restored_from=first,
    )
    git.run(root, "add", "--", "knowledge/a.md")
    git.run(root, "commit", "-m", message(trailers))

    repo = vault_repository()
    head = repo.log(limit=1)[0]
    assert head.version not in (first, second)
    assert head.meta.writer == WRITER_AGENT
    assert (head.meta.operation, head.meta.restored_from) == (OP_RESTORE, first)
    assert repo.read("HEAD", "knowledge/a.md") == b"one\n"
    # No earlier commit was rewritten.
    assert [c.version for c in repo.log()][1:3] == [second, first]


async def test_the_routes_need_the_token(client: AsyncClient) -> None:
    async with client:
        problems = await client.get(
            "/api/v1/vault/problems", headers={"X-Coffer-Token": "not-the-token"}
        )
        handoff = await client.post(
            "/api/v1/vault/history/handoff",
            json={"path": "knowledge/a.md"},
            headers={"X-Coffer-Token": "not-the-token"},
        )
    assert problems.status_code == 401
    assert handoff.status_code == 401


async def test_the_routes_that_listed_diffed_and_restored_versions_are_gone(
    client: AsyncClient,
) -> None:
    async with client:
        gone = [
            await client.get("/api/v1/vault/history", params={"path": "knowledge/a.md"}),
            await client.get("/api/v1/vault/diff", params={"path": "a", "version": "abcd"}),
            await client.get("/api/v1/vault/content", params={"path": "knowledge/a.md"}),
            await client.get("/api/v1/vault/changes"),
            await client.post("/api/v1/vault/restore", json={}),
        ]
    assert [r.status_code for r in gone] == [404, 404, 404, 404, 404]
