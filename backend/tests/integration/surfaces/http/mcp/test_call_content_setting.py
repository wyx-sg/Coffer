"""Settings > Data > History's switch for recording tool call content
(spec mcp-gateway "Switch call content recording per machine")."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.mcp import call_content
from coffer.application.mcp.call_content import CallContentRecording
from coffer.infrastructure.daemon.call_content_setting import DaemonConfigCallContent
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.mcp.call_content_routes import router

TOKEN = "test-token"


class _Audit:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    async def record(self, event: str, *, details: dict[str, Any], **_: Any) -> None:
        self.rows.append((event, details))


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".coffer").mkdir()
    call_content.configure(CallContentRecording(DaemonConfigCallContent()))
    yield tmp_path
    call_content.configure(None)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="recording is on by default and can be switched off"
)
async def test_recording_is_on_by_default_and_switches_off(home: Path) -> None:
    audit = _Audit()
    set_active_token(TOKEN)
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(router)
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_actor] = lambda: "ui"
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
    ) as client:
        assert (await client.get("/api/v1/settings/call-content")).json() == {"enabled": True}
        assert call_content.call_content({"arguments": {"a": 1}}) is not None

        r = await client.put("/api/v1/settings/call-content", json={"enabled": False})
        assert r.json() == {"enabled": False}
        # The next call, in any session, records no content.
        assert call_content.call_content({"arguments": {"a": 1}}) is None
        # Kept for the next start, beside the file's other keys.
        stored = json.loads((home / ".coffer" / "daemon-config.json").read_text())
        assert stored["record_call_content"] is False
        assert CallContentRecording(DaemonConfigCallContent()).enabled is False

    assert audit.rows == [("call_content_recording_updated", {"from": True, "to": False})]
