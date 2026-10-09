"""The whole daemon on a fake home, for the memory-hook integration tests
(spec memory "Retrieve the notes a prompt names", "Count what memory delivered
and what was read").

:func:`boot` starts ``create_app`` with every root Coffer writes under pointed
into ``tmp_path`` (``HOME`` included), the ``memory`` feature on, and both of the
CLI's ways to reach a daemon routed at one ``TestClient``: the person-facing
commands through ``client_or_exit``, and ``coffer memory hook`` — which only
ever calls ``live_daemon`` and ``httpx.post`` — through those two names.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

import coffer.surfaces.cli._client as _cli_client
import coffer.surfaces.cli.memory_hook_cmd as memory_hook_cmd
from coffer.domain.memory.note import Note
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.memory import store
from coffer.surfaces.http import feature_dependencies
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.integration.memory.conftest import claude_code_config, init_repository
from tests.support.features import enable_all_in_config
from tests.unit.memory._delivery_corpus import filler_notes, node20_note

TOKEN = "test-token-memory-hook"
PORT = 59960

_CC_PROJECT = """---
name: python-lockfile
description: Dependencies are locked with uv
metadata:
  type: project
---

Run `uv sync --frozen` in this project; a plain `pip install` drifts.
"""

_CC_PERSONAL = """---
name: worktree-development
description: Always develop in a git worktree
metadata:
  type: user
---

Multiple parallel sessions share the repo — always work in a worktree.
"""


class _PersistentClient:
    def __init__(self, inner: TestClient) -> None:
        self._inner = inner

    def __enter__(self) -> _PersistentClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


@dataclass
class HookApp:
    client: TestClient
    home: pathlib.Path
    info: DaemonInfo
    #: Every body ``coffer memory hook`` posted to the daemon.
    posts: list[dict[str, Any]]


def boot(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HookApp]:
    home = tmp_path
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(PORT))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(PORT + 9))
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    (home / ".coffer").mkdir(parents=True, exist_ok=True)
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".codex").mkdir(parents=True, exist_ok=True)
    prior_features = feature_dependencies._feature_service
    enable_all_in_config()

    app = create_app()
    set_active_token(TOKEN)
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=PORT,
        token=TOKEN,
        started_at=datetime.now(tz=UTC),
    )
    client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": TOKEN, "X-Coffer-Actor": "user"},
        raise_server_exceptions=False,
    )
    client.__enter__()
    posts: list[dict[str, Any]] = []

    def _post(url: str, *, json: Any = None, headers: Any = None, timeout: Any = None) -> Any:
        posts.append(json)
        path = url.split("/api/v1", 1)[1]
        return client.post(path, json=json, headers=headers)

    monkeypatch.setattr(
        _cli_client, "client_or_exit", lambda **_kw: (_PersistentClient(client), info)
    )
    monkeypatch.setattr(memory_hook_cmd, "live_daemon", lambda: info)
    monkeypatch.setattr(httpx, "post", _post)
    try:
        yield HookApp(client=client, home=home, info=info, posts=posts)
    finally:
        client.__exit__(None, None, None)
        set_active_token(None)
        feature_dependencies._feature_service = prior_features


def register(c: TestClient, agent_type: str) -> str:
    r = c.post("/agents", json={"type": agent_type})
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def partitions(c: TestClient) -> dict[str, dict[str, Any]]:
    r = c.get("/memory/partitions")
    assert r.status_code == 200, r.text
    return {p["name"]: p for p in r.json()["partitions"]}


def seed_repository(app: HookApp) -> pathlib.Path:
    """A real repository with a project and a personal Claude Code memory."""
    repo = init_repository(app.home / "work" / "coffer")
    claude_code_config(
        app.home / ".claude",
        repo,
        {"python-lockfile.md": _CC_PROJECT, "worktree-development.md": _CC_PERSONAL},
    )
    return repo


def sync(c: TestClient) -> dict[str, Any]:
    r = c.post("/memory/sync")
    assert r.status_code == 200, r.text
    return dict(r.json())


def distilled(app: HookApp) -> tuple[pathlib.Path, str]:
    """Seed, sync, then pad the repository partition and ``global`` to a
    realistic corpus holding the Node 20 note. Returns the repository and its
    partition's name."""
    repo = seed_repository(app)
    sync(app.client)
    name = next(n for n in partitions(app.client) if n != "global")
    notes: list[Note] = [*filler_notes(name), *filler_notes("global", offset=12)]
    notes.append(node20_note(name))
    for n in notes:
        store.write_note(n)
    return repo, name


def fire(c: TestClient, agent_uid: str, event: str, **kw: str) -> dict[str, Any] | None:
    r = c.post("/memory/hook", json={"agent_uid": agent_uid, "event": event, **kw})
    assert r.status_code == 200, r.text
    out = r.json()["output"]
    return dict(out) if out is not None else None


def audit(c: TestClient, event_type: str) -> list[dict[str, Any]]:
    r = c.get("/audit", params={"event_type": event_type, "limit": 200})
    assert r.status_code == 200, r.text
    return list(r.json()["entries"])


def extract_json(output: str) -> Any:
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return json.loads("".join(lines[i:]))
    return json.loads(output)


__all__ = [
    "PORT",
    "TOKEN",
    "HookApp",
    "audit",
    "boot",
    "distilled",
    "extract_json",
    "fire",
    "partitions",
    "register",
    "seed_repository",
    "sync",
]
