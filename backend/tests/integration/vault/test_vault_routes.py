"""``/api/v1/vault`` — history, diff, content, restore and recent changes of
any vault file (coffer.surfaces.http.vault_routes; spec vault-storage "Show,
compare and restore any version of a vault file").

The headline case runs the whole app: a skill file saved twice through the
skill editor has two versions naming their writer, and a restore is a new
commit through the same compare-and-swap. The rest run the router alone over
the vault writer. Every test runs in its own HOME (tests/conftest.py).
"""

from __future__ import annotations

import pathlib
import textwrap
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from coffer.domain.vault.content_ids import fingerprint
from coffer.domain.vault.writers import WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_repository, vault_writer
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.vault_routes import router as vault_router

TOKEN = "t-vault-routes"
USER = CommitMeta(writer=WRITER_USER, operation="edit", summary="Saved", actor="ui")


def _mounted(app: FastAPI) -> FastAPI:
    """The app with the vault router, unless the route table already has it."""
    if not any(getattr(r, "path", "").startswith("/api/v1/vault/") for r in app.routes):
        app.include_router(vault_router)
    return app


# --- the whole app: a skill file's history ------------------------------------


def _skill_folder(folder: pathlib.Path, name: str) -> pathlib.Path:
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: A skill named {name}.
            ---

            first
            """
        )
    )
    return folder


def test_a_skill_file_saved_twice_has_two_versions_and_restores_as_a_new_one(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59900")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59909")
    set_active_token(TOKEN)
    app = _mounted(create_app())
    src = _skill_folder(tmp_path / "src", "hist-skill")
    path = "skills/hist-skill/SKILL.md"
    with TestClient(app, headers={"X-Coffer-Token": TOKEN}) as c:
        r = c.post("/api/v1/skills/import", json={"path": str(src)})
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]
        vault_writer().settle()  # the import, as the scanner would find it

        fp = c.get(f"/api/v1/skills/{uid}/files/content", params={"path": "SKILL.md"})
        fp = fp.json()["fingerprint"]
        saved: list[dict[str, Any]] = []
        for text in ("second\n", "third\n"):
            r = c.put(
                f"/api/v1/skills/{uid}/files/content",
                json={"path": "SKILL.md", "content": text, "expected_fingerprint": fp},
            )
            assert r.status_code == 200, r.text
            fp = r.json()["fingerprint"]
            saved.append(r.json())

        r = c.get("/api/v1/vault/history", params={"path": path})
        assert r.status_code == 200, r.text
        versions = r.json()["versions"]
        saves, older = versions[:2], versions[2:]
        assert [v["writer"] for v in saves] == ["user", "user"]
        assert [v["display_writer"] for v in saves] == ["user", "user"]
        assert [[(p["path"], p["status"]) for p in v["paths"]] for v in saves] == [
            [(path, "modified")]
        ] * 2
        assert older, "the imported version is listed too"
        newest, first_save = saves[0]["version"], saves[1]["version"]

        # The save's audit row names the commit it made.
        audit = c.get("/api/v1/audit", params={"event_type": "skill_updated"}).json()
        assert newest in {e["details"].get("version") for e in audit["entries"]}

        r = c.get("/api/v1/vault/diff", params={"path": path, "version": newest})
        assert r.status_code == 200, r.text
        assert "-second" in r.json()["diff"] and "+third" in r.json()["diff"]

        r = c.get("/api/v1/vault/content", params={"path": path, "version": first_save})
        assert r.json()["content"].endswith("second\n")

        # A stale fingerprint is refused and changes nothing.
        r = c.post(
            "/api/v1/vault/restore",
            json={"path": path, "version": first_save, "expected_fingerprint": "0" * 64},
        )
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "VAULT_FILE_STALE"
        assert vault_repository().head() == newest

        now = c.get("/api/v1/vault/content", params={"path": path}).json()
        assert now["version"] is None and now["fingerprint"] == fp
        r = c.post(
            "/api/v1/vault/restore",
            json={"path": path, "version": first_save, "expected_fingerprint": now["fingerprint"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["restored_from"] == first_save and body["paths"] == [path]
        head = vault_repository().log(limit=1)[0]
        assert head.version == body["version"] and head.meta.restored_from == first_save
        assert head.meta.writer == WRITER_USER
        assert (vault_root() / path).read_text().endswith("second\n")
        # History was added to, never rewritten.
        again = c.get("/api/v1/vault/history", params={"path": path}).json()["versions"]
        assert [v["version"] for v in again[1:]] == [v["version"] for v in versions]
        assert again[0]["restored_from"] == first_save

        audit = c.get("/api/v1/audit", params={"event_type": "vault_file_restored"}).json()
        (row,) = audit["entries"]
        assert row["details"]["restored_from"] == first_save


# --- the router alone ------------------------------------------------------------


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


def _write(path: str, data: bytes, expected: str | Expect = Expect.HEAD) -> str:
    version = vault_writer().write_file(path, data, meta=USER, expected=expected)
    assert version is not None
    return version


async def test_restoring_a_folder_removes_files_the_version_did_not_have(
    client: AsyncClient, audit: _Audit
) -> None:
    first = _write("skills/pdf/SKILL.md", b"v1\n", Expect.ABSENT)
    _write("skills/pdf/SKILL.md", b"v2\n")
    _write("skills/pdf/extra.md", b"later\n", Expect.ABSENT)
    async with client:
        history = await client.get("/api/v1/vault/history", params={"path": "skills/pdf/"})
        assert [len(v["paths"]) for v in history.json()["versions"]] == [1, 1, 1]
        r = await client.post(
            "/api/v1/vault/restore",
            json={"path": "skills/pdf/", "version": first, "expected_fingerprint": None},
        )
    assert r.status_code == 200, r.text
    assert sorted(r.json()["paths"]) == ["skills/pdf/SKILL.md", "skills/pdf/extra.md"]
    assert sorted(vault_repository().tree("HEAD", "skills/pdf/")) == ["skills/pdf/SKILL.md"]
    assert not (vault_root() / "skills/pdf/extra.md").exists()
    assert [e[0] for e in audit.events] == ["vault_file_restored"]
    assert audit.events[0][1] == "ui"


async def test_restore_of_a_file_states_what_it_read(client: AsyncClient) -> None:
    first = _write("knowledge/a.md", b"one\n", Expect.ABSENT)
    _write("knowledge/a.md", b"two\n")
    async with client:
        stale = await client.post(
            "/api/v1/vault/restore",
            json={"path": "knowledge/a.md", "version": first, "expected_fingerprint": None},
        )
        good = await client.post(
            "/api/v1/vault/restore",
            json={
                "path": "knowledge/a.md",
                "version": first,
                "expected_fingerprint": fingerprint(b"two\n"),
            },
        )
    assert stale.status_code == 409, stale.text
    assert good.status_code == 200, good.text
    assert (vault_root() / "knowledge/a.md").read_bytes() == b"one\n"


@pytest.mark.acceptance(
    spec="vault-storage", scenario="recent changes list the vault's commits newest first"
)
async def test_content_diff_and_changes(client: AsyncClient) -> None:
    first = _write("knowledge/a.md", b"one\n", Expect.ABSENT)
    _write("skills/x/SKILL.md", b"x\n", Expect.ABSENT)
    async with client:
        content = await client.get(
            "/api/v1/vault/content", params={"path": "knowledge/a.md", "version": first}
        )
        missing = await client.get(
            "/api/v1/vault/content", params={"path": "knowledge/a.md", "version": "f" * 40}
        )
        not_a_version = await client.get(
            "/api/v1/vault/diff", params={"path": "knowledge/a.md", "version": "HEAD~1"}
        )
        changes = await client.get("/api/v1/vault/changes", params={"prefix": "knowledge"})
        everything = await client.get("/api/v1/vault/changes", params={"limit": 2})
    assert content.json() == {
        "path": "knowledge/a.md",
        "version": first,
        "content": "one\n",
        "binary": False,
        "size": 4,
        "fingerprint": fingerprint(b"one\n"),
    }
    assert missing.status_code == 404
    assert not_a_version.status_code == 404
    assert [c["version"] for c in changes.json()["changes"]] == [first]
    assert changes.json()["changes"][0]["paths"][0]["path"] == "knowledge/a.md"
    assert len(everything.json()["changes"]) == 2
    assert everything.json()["next_cursor"] == "2"  # the first commit is older still


async def test_secret_ciphertext_and_paths_outside_the_vault_are_refused(
    client: AsyncClient,
) -> None:
    first = _write("knowledge/a.md", b"one\n", Expect.ABSENT)
    async with client:
        secret = await client.get("/api/v1/vault/content", params={"path": "secret/github.enc"})
        escape = await client.get("/api/v1/vault/history", params={"path": "../etc/passwd"})
        restore = await client.post(
            "/api/v1/vault/restore",
            json={"path": "secret/x.enc", "version": first, "expected_fingerprint": None},
        )
    assert secret.status_code == 400 and secret.json()["error"]["code"] == "VAULT_PATH_INVALID"
    assert escape.status_code == 400
    assert restore.status_code == 400


async def test_the_routes_need_the_token(client: AsyncClient) -> None:
    async with client:
        r = await client.get("/api/v1/vault/problems", headers={"X-Coffer-Token": "not-the-token"})
    assert r.status_code == 401
