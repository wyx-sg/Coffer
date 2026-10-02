"""A real ``create_app`` daemon behind the CLI client, for the top-level
``config``/``log``/``path``/``scan`` tests.

The whole app rather than a hand-wired subset, because those commands compose
reads from several kinds' routes and claim the same effect and the same audit
entry as the page. Every root Coffer writes under is pointed into ``tmp_path``
so nothing reaches the real ``~/.coffer``.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.testclient import TestClient

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-top-level-cli"


class _PersistentClient:
    """The CLI closes its client after every command; the app's lifespan must
    outlive the whole test, so each command gets a shell over one client."""

    def __init__(self, inner: TestClient) -> None:
        self._inner = inner

    def __enter__(self) -> _PersistentClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


#: A ``COFFER_FEATURES`` value that pins nothing.
NO_PIN = ""


def boot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, *, features: str | None = None
) -> Iterator[TestClient]:
    """Yield an HTTP client on a real app whose CLI client points at it.

    ``features`` is the ``COFFER_FEATURES`` pin the daemon boots with; left
    out, it keeps the suite's own (every feature on, ``tests/conftest.py``).
    ``NO_PIN`` boots it with none, so each feature is decided by the machine's
    setting and then by its default, off.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59940")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59949")
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path / "logs"))
    if features is not None:
        monkeypatch.setenv("COFFER_FEATURES", features)

    app = create_app()
    set_active_token(_TOKEN)
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59940,
        token=_TOKEN,
        started_at=datetime.now(tz=UTC),
        binary_path="/test",
    )
    client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    client.__enter__()
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_PersistentClient(client), info))
    try:
        yield client
    finally:
        client.__exit__(None, None, None)
        set_active_token(None)


def extract_json(output: str) -> Any:
    """The JSON document in ``output``, past any log lines the in-process
    lifespan wrote to the same captured stream."""
    import json

    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return json.loads("".join(lines[i:]))
    return json.loads(output)


def audit(client: TestClient, event_type: str) -> list[dict[str, Any]]:
    r = client.get("/audit", params={"event_type": event_type})
    assert r.status_code == 200, r.text
    return list(r.json()["entries"])
