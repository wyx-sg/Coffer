"""Integration tests for `coffer memory ...` CLI subcommands.

TEST26-013: every verb (`create` / `list` / `describe` / `add` /
`list-memories` / `edit` / `delete` / `clear` / `search` / `delete-store`)
plus the `--json` switch where it exists.

We boot the full FastAPI app (via ``create_app``) so the memory kind is
wired with the production routes + on_delete hook, then route
``_cli_client.client_or_exit`` to a Starlette ``TestClient`` against that
app. The mem0 engine is replaced with a ``FakeMemoryStore`` so no LLM
backend is required.

Spec 007 §User Story 7 — CLI mirrors the REST surface.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt
from typing import cast

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.domain.memory.record import Actor
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import (
    get_memory_service,
    get_resource_service,
)
from tests.integration.memory.fakes import FakeMemoryStore

_runner = CliRunner()
_TOKEN = "test-token-memory-cli"


def _extract_json(output: str) -> str:
    """Strip leading log lines so JSON can be decoded.

    Same approach as ``test_skill_cmd.py``: the in-process FastAPI lifespan
    emits alembic INFO logs that get mingled with the CLI's stdout under
    CliRunner. Skip until the first line starting with a JSON sentinel.
    """
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return "".join(lines[i:])
    return output


class _StubMemoryService:
    """Stand-in for ``MemoryService`` so the CLI's HTTP calls never reach
    the real mem0 engine. Mirrors the FakeMemoryStore semantics at the
    service layer — the routes call this directly via dependency_overrides.

    Each call verifies the store Resource exists (mirrors production
    ``MemoryService.get_store_config``), raising ``MemoryStoreNotFound``
    when missing so the CLI sees the same 404 envelope it would in
    production.
    """

    def __init__(self, resource_service) -> None:  # type: ignore[no-untyped-def]
        self._store = FakeMemoryStore()
        self._resources = resource_service
        self._opened: set[str] = set()

    async def _ensure_store(self, store_name: str) -> None:
        from coffer.domain.errors import MemoryStoreNotFound, ResourceNotFound
        from coffer.domain.memory.config import MemoryStoreConfig
        from coffer.domain.resource import ResourceRef

        try:
            await self._resources.get(ResourceRef("memory", store_name))
        except ResourceNotFound as exc:
            raise MemoryStoreNotFound(store_name) from exc
        if store_name not in self._opened:
            await self._store.open(store_name, MemoryStoreConfig())
            self._opened.add(store_name)

    async def add(self, *, store_name: str, text: str, actor: str):
        await self._ensure_store(store_name)
        return await self._store.add(store_name, text, actor)  # type: ignore[arg-type]

    async def list_memories(self, *, store_name: str, limit: int, offset: int):
        await self._ensure_store(store_name)
        rows = list(await self._store.list(store_name, limit=limit, offset=offset))
        total = len(self._store._stores.get(store_name, {}))  # type: ignore[attr-defined]
        return rows, total

    async def get(self, *, store_name: str, memory_id: str):
        await self._ensure_store(store_name)
        m = await self._store.get(store_name, memory_id)
        if m is None:
            from coffer.domain.errors import MemoryNotFound

            raise MemoryNotFound(store_name, memory_id)
        return m

    async def update(self, *, store_name: str, memory_id: str, new_text: str, actor: str):
        await self._ensure_store(store_name)
        try:
            # CODE26-023: protocol requires actor as keyword-only.
            return await self._store.update(
                store_name, memory_id, new_text, actor=cast(Actor, actor)
            )
        except KeyError as exc:
            from coffer.domain.errors import MemoryNotFound

            raise MemoryNotFound(store_name, memory_id) from exc

    async def delete(self, *, store_name: str, memory_id: str, actor: str) -> None:
        await self._ensure_store(store_name)
        ok = await self._store.delete(store_name, memory_id)
        if not ok:
            from coffer.domain.errors import MemoryNotFound

            raise MemoryNotFound(store_name, memory_id)

    async def clear(self, *, store_name: str, actor: str) -> int:
        await self._ensure_store(store_name)
        return await self._store.clear(store_name)

    async def search(self, *, store_name: str, query: str, top_k: int):
        await self._ensure_store(store_name)
        return list(await self._store.search(store_name, query, top_k))

    async def metrics(self, *, store_name: str):
        await self._ensure_store(store_name)
        n = len(self._store._stores.get(store_name, {}))  # type: ignore[attr-defined]
        return n, 0  # disk_bytes = 0 in the fake


@pytest.fixture
def memory_cli_daemon(tmp_path, monkeypatch):
    """In-process daemon plumbed through the CLI client, with a stubbed
    MemoryService so no mem0/LLM backend is required.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59800")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59809")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))

    app = create_app()
    # ``get_resource_service`` is wired during the app lifespan (alembic +
    # composition root). We need it to look up the Resource before any
    # memory operation so the stub mirrors production "store missing → 404"
    # semantics — defer the wire-up until inside the lifespan.
    stub_holder: dict[str, _StubMemoryService] = {}

    def _build_stub() -> _StubMemoryService:
        if "svc" not in stub_holder:
            stub_holder["svc"] = _StubMemoryService(get_resource_service())
        return stub_holder["svc"]

    app.dependency_overrides[get_memory_service] = _build_stub
    set_active_token(_TOKEN)

    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59800,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )

    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    fake_client.__enter__()

    class _PersistentClient:
        def __init__(self, inner: TestClient) -> None:
            self._inner = inner

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(self._inner, item)

    monkeypatch.setattr(
        _cli_client,
        "client_or_exit",
        lambda: (_PersistentClient(fake_client), info),
    )

    yield tmp_path

    fake_client.__exit__(None, None, None)
    set_active_token(None)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_memory_create_with_ollama(memory_cli_daemon):
    r = _runner.invoke(
        cli_app,
        [
            "memory",
            "create",
            "prefs",
            "--llm-provider",
            "ollama",
            "--llm-model",
            "llama3.1",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "created: memory:prefs" in r.output


def test_memory_create_default_provider_is_none(memory_cli_daemon):
    """Default --llm-provider is `none`; create still succeeds."""
    r = _runner.invoke(cli_app, ["memory", "create", "store-none"])
    assert r.exit_code == 0, r.output


def test_memory_create_duplicate_exits_5(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "dup", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(
        cli_app,
        ["memory", "create", "dup", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    assert r.exit_code == 5, r.output


def test_memory_create_invalid_config_exits_6(memory_cli_daemon):
    """Provider=ollama requires --llm-model; missing it → 422 → exit 6."""
    r = _runner.invoke(cli_app, ["memory", "create", "bad", "--llm-provider", "ollama"])
    assert r.exit_code == 6, r.output


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_memory_list_json(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "s1", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(cli_app, ["memory", "list", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(_extract_json(r.output))
    assert any(s["name"] == "s1" for s in data["memory_stores"])


def test_memory_list_table(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "tbl", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(cli_app, ["memory", "list"])
    assert r.exit_code == 0, r.output
    assert "tbl" in r.output


# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------


def test_memory_describe_text(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "desc1", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(cli_app, ["memory", "describe", "desc1"])
    assert r.exit_code == 0, r.output
    assert "desc1" in r.output
    assert "memories:" in r.output


def test_memory_describe_json(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "desc2", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(cli_app, ["memory", "describe", "desc2", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(_extract_json(r.output))
    assert data["memory_store"]["name"] == "desc2"
    assert "metrics" in data


def test_memory_describe_not_found(memory_cli_daemon):
    r = _runner.invoke(cli_app, ["memory", "describe", "ghost"])
    assert r.exit_code == 4, r.output


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def test_memory_add_success(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "addok", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(cli_app, ["memory", "add", "addok", "the user uses tabs"])
    assert r.exit_code == 0, r.output
    assert "added memory id=" in r.output


def test_memory_add_store_missing(memory_cli_daemon):
    r = _runner.invoke(cli_app, ["memory", "add", "ghost", "hello"])
    assert r.exit_code == 4, r.output


# ---------------------------------------------------------------------------
# list-memories
# ---------------------------------------------------------------------------


def test_memory_list_memories_json(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "lm", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    _runner.invoke(cli_app, ["memory", "add", "lm", "fact one"])
    _runner.invoke(cli_app, ["memory", "add", "lm", "fact two"])
    r = _runner.invoke(cli_app, ["memory", "list-memories", "lm", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(_extract_json(r.output))
    assert data["total"] == 2
    assert {m["text"] for m in data["memories"]} == {"fact one", "fact two"}


def test_memory_list_memories_table(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "lmt", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    _runner.invoke(cli_app, ["memory", "add", "lmt", "a fact"])
    r = _runner.invoke(cli_app, ["memory", "list-memories", "lmt"])
    assert r.exit_code == 0, r.output
    assert "a fact" in r.output


def test_memory_list_memories_store_missing(memory_cli_daemon):
    r = _runner.invoke(cli_app, ["memory", "list-memories", "ghost"])
    assert r.exit_code == 4, r.output


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


def _fetch_one_memory_id(store: str) -> str:
    """Pull the first memory id out of `memory list-memories <store> --json`.

    The plain `add` verb prints `added memory id=<id>` but the alembic-log
    interleaving under CliRunner makes substring parsing brittle; the JSON
    list is the deterministic source of truth.
    """
    r = _runner.invoke(cli_app, ["memory", "list-memories", store, "--json"])
    data = json.loads(_extract_json(r.output))
    return str(data["memories"][0]["id"])


def test_memory_edit_success(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "ed", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    _runner.invoke(cli_app, ["memory", "add", "ed", "before"])
    mid = _fetch_one_memory_id("ed")
    r = _runner.invoke(cli_app, ["memory", "edit", "ed", mid, "after"])
    assert r.exit_code == 0, r.output
    assert "updated" in r.output


def test_memory_edit_not_found(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "ed2", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(cli_app, ["memory", "edit", "ed2", "ghost", "x"])
    assert r.exit_code == 4, r.output


# ---------------------------------------------------------------------------
# delete (single memory)
# ---------------------------------------------------------------------------


def test_memory_delete_single(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "dl", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    _runner.invoke(cli_app, ["memory", "add", "dl", "hello"])
    mid = _fetch_one_memory_id("dl")
    r = _runner.invoke(cli_app, ["memory", "delete", "dl", mid])
    assert r.exit_code == 0, r.output
    assert "deleted" in r.output


def test_memory_delete_not_found(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "dlnf", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(cli_app, ["memory", "delete", "dlnf", "ghost"])
    assert r.exit_code == 4, r.output


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


def test_memory_clear_with_yes(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "cl", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    _runner.invoke(cli_app, ["memory", "add", "cl", "a"])
    _runner.invoke(cli_app, ["memory", "add", "cl", "b"])
    r = _runner.invoke(cli_app, ["memory", "clear", "cl", "--yes"])
    assert r.exit_code == 0, r.output
    assert "cleared" in r.output


def test_memory_clear_aborts_without_yes(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "cl2", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(cli_app, ["memory", "clear", "cl2"], input="n\n")
    assert r.exit_code == 1, r.output


def test_memory_clear_not_found(memory_cli_daemon):
    r = _runner.invoke(cli_app, ["memory", "clear", "ghost", "--yes"])
    assert r.exit_code == 4, r.output


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_memory_search_text(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "sr", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    _runner.invoke(cli_app, ["memory", "add", "sr", "the user uses tabs"])
    _runner.invoke(cli_app, ["memory", "add", "sr", "another fact"])
    r = _runner.invoke(cli_app, ["memory", "search", "sr", "tabs"])
    assert r.exit_code == 0, r.output
    assert "tabs" in r.output


def test_memory_search_json_with_top_k(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "sr2", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    _runner.invoke(cli_app, ["memory", "add", "sr2", "alpha"])
    r = _runner.invoke(
        cli_app,
        ["memory", "search", "sr2", "alpha", "--top-k", "1", "--json"],
    )
    assert r.exit_code == 0, r.output
    data = json.loads(_extract_json(r.output))
    assert "hits" in data


def test_memory_search_not_found(memory_cli_daemon):
    r = _runner.invoke(cli_app, ["memory", "search", "ghost", "q"])
    assert r.exit_code == 4, r.output


# ---------------------------------------------------------------------------
# delete-store
# ---------------------------------------------------------------------------


def test_memory_delete_store_with_yes(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "ds", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(cli_app, ["memory", "delete-store", "ds", "--yes"])
    assert r.exit_code == 0, r.output
    assert "deleted: memory:ds" in r.output
    # And the store is gone — describe returns 404.
    describe = _runner.invoke(cli_app, ["memory", "describe", "ds"])
    assert describe.exit_code == 4


def test_memory_delete_store_aborts_without_yes(memory_cli_daemon):
    _runner.invoke(
        cli_app,
        ["memory", "create", "ds2", "--llm-provider", "ollama", "--llm-model", "x"],
    )
    r = _runner.invoke(cli_app, ["memory", "delete-store", "ds2"], input="n\n")
    assert r.exit_code == 1, r.output


def test_memory_delete_store_not_found(memory_cli_daemon):
    r = _runner.invoke(cli_app, ["memory", "delete-store", "ghost", "--yes"])
    assert r.exit_code == 4, r.output
