"""Integration tests for `coffer chat` CLI commands.

NOTE ON LLM CALLS: These tests do NOT make real LLM calls.
- Conversation creation and model CRUD paths are fully testable.
- The SSE turn path is tested via the FakeAgentAdapter (scripted events).
- The "no model configured" path produces a clear CLI error message.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC
from datetime import datetime as dt

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.application.chat.turn_orchestrator import clear_active_turns
from coffer.domain.chat.events import (
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write
from coffer.surfaces.cli.main import app
from coffer.surfaces.http.auth import set_active_token

from .conftest import _build_chat_app

_runner = CliRunner()
_TOKEN = "test-token-chat-cmd"
_PORT = 8002


@pytest.fixture(autouse=True)
def _reset_turns() -> Generator[None, None, None]:
    """Clear lingering active turns between tests."""
    clear_active_turns()
    yield
    clear_active_turns()


@pytest.fixture(autouse=True)
def _reset_token() -> Generator[None, None, None]:
    """Ensure the active token is cleaned up after every test."""
    yield
    set_active_token(None)


def _make_fixture(
    tmp_path: object,
    monkeypatch: object,
    events: list | None = None,
) -> TestClient:
    """Helper to build and monkeypatch the in-process daemon for chat tests.

    Uses the shared _build_chat_app builder from conftest to avoid duplication.
    When custom ``events`` are provided the TurnOrchestrator is replaced with
    a fresh one backed by those events; otherwise the default scripted events
    from _build_chat_app are used.
    """
    home = tmp_path / "home"  # type: ignore[operator]
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))  # type: ignore[union-attr]

    fapp = _build_chat_app()

    if events is not None:
        # Override the chat services to use caller-supplied agent events.
        from coffer.surfaces.http.dependencies import (
            get_agent_registry,
            get_chat_service,
            get_model_service,
            get_turn_orchestrator,
        )
        from tests.unit.chat.conftest import make_chat_services

        chat_svc, model_svc, orchestrator, registry = make_chat_services(events)
        fapp.dependency_overrides[get_chat_service] = lambda: chat_svc
        fapp.dependency_overrides[get_model_service] = lambda: model_svc
        fapp.dependency_overrides[get_turn_orchestrator] = lambda: orchestrator
        fapp.dependency_overrides[get_agent_registry] = lambda: registry

    set_active_token(_TOKEN)

    daemon_json_dir = home / ".coffer"
    daemon_json_dir.mkdir(parents=True, exist_ok=True)
    info = DaemonInfo(
        version=1,
        pid=12346,
        port=_PORT,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    write(home / ".coffer" / "daemon.json", info)

    fake_client = TestClient(
        fapp,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN},
        raise_server_exceptions=False,
    )

    from coffer.surfaces.cli import _client as _cli_client

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, info))  # type: ignore[union-attr]

    return fake_client


# ---------------------------------------------------------------------------
# No model configured path
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="008-agent-chat", scenario="no-model empty state")
def test_chat_no_model_configured_gives_helpful_error(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """When no model is configured, exit code should be 1 with a helpful message."""
    _make_fixture(tmp_path, monkeypatch)

    result = _runner.invoke(app, ["chat", "-m", "hello"])
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "model" in combined.lower()


# ---------------------------------------------------------------------------
# Conversation creation and SSE turn
# ---------------------------------------------------------------------------


def test_chat_creates_conversation(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """coffer chat -m should succeed when a model is registered."""
    fake_client = _make_fixture(tmp_path, monkeypatch)

    # Register a model first via the fake HTTP client
    r = fake_client.post(
        "/models",
        json={
            "display_name": "Test",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "credential_ref": "ref",
        },
    )
    assert r.status_code == 201, r.text

    result = _runner.invoke(app, ["chat", "-m", "hello"])
    assert result.exit_code == 0, result.output
    # The FakeAgentAdapter emits "Hello from agent!" as TextDelta
    assert "Hello from agent!" in result.output


def test_chat_resume_conversation(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """coffer chat --conversation <id> -m should resume an existing conversation."""
    fake_client = _make_fixture(tmp_path, monkeypatch)

    # Register a model
    fake_client.post(
        "/models",
        json={
            "display_name": "Test",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "credential_ref": "ref",
        },
    )

    # Create a conversation first
    r = fake_client.post("/chat/conversations")
    assert r.status_code == 201
    conv_id = r.json()["id"]

    # Send via CLI using that conversation
    result = _runner.invoke(app, ["chat", "--conversation", conv_id, "-m", "hello again"])
    assert result.exit_code == 0, result.output
    assert "Hello from agent!" in result.output


# ---------------------------------------------------------------------------
# SSE streaming output
# ---------------------------------------------------------------------------


def test_chat_streams_text_delta(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The CLI should print the text_delta content to stdout."""
    events = [
        TurnStarted(),
        TextDelta(text="First chunk "),
        TextDelta(text="second chunk"),
        TurnDone(prompt_tokens=5, completion_tokens=5, stop_reason="end_turn"),
    ]
    fake_client = _make_fixture(tmp_path, monkeypatch, events=events)

    fake_client.post(
        "/models",
        json={
            "display_name": "T",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "credential_ref": "ref",
        },
    )

    result = _runner.invoke(app, ["chat", "-m", "hi"])
    assert result.exit_code == 0, result.output
    assert "First chunk" in result.output
    assert "second chunk" in result.output


def test_chat_renders_tool_call_and_result(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The CLI prints tool_call and tool_result events as they stream."""
    events = [
        TurnStarted(),
        ToolCall(tool_use_id="t1", tool_name="coffer__search_memory", tool_input={"q": "oauth"}),
        ToolResult(
            tool_use_id="t1",
            tool_name="coffer__search_memory",
            output={"hits": 1},
            error=None,
        ),
        TextDelta(text="found it"),
        TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn"),
    ]
    fake_client = _make_fixture(tmp_path, monkeypatch, events=events)
    fake_client.post(
        "/models",
        json={
            "display_name": "T",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "credential_ref": "ref",
        },
    )

    result = _runner.invoke(app, ["chat", "-m", "hi"])
    assert result.exit_code == 0, result.output
    assert "[tool_call] coffer__search_memory" in result.output
    assert "[tool_result] coffer__search_memory" in result.output
    assert "found it" in result.output


def test_chat_renders_turn_error(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A turn_error event prints an error message and exits non-zero."""
    events = [
        TurnStarted(),
        TurnError(code="AGENT_ERROR", message="provider exploded"),
    ]
    fake_client = _make_fixture(tmp_path, monkeypatch, events=events)
    fake_client.post(
        "/models",
        json={
            "display_name": "T",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "credential_ref": "ref",
        },
    )

    result = _runner.invoke(app, ["chat", "-m", "hi"])
    assert result.exit_code == 1
    assert "AGENT_ERROR" in result.output
    assert "provider exploded" in result.output


# ---------------------------------------------------------------------------
# Integration: model CRUD then chat
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="008-agent-chat", scenario="command-line parity for chat and models")
def test_model_add_then_chat(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Full workflow: add a model via CLI then chat via CLI."""
    _make_fixture(tmp_path, monkeypatch)

    # Add model via CLI (option form, per quickstart.md)
    r = _runner.invoke(
        app,
        [
            "model",
            "add",
            "--provider",
            "anthropic",
            "--model",
            "claude-sonnet-4-6",
            "--name",
            "MyClaude",
            "--credential-ref",
            "my-key",
        ],
    )
    assert r.exit_code == 0, r.output

    # Verify it's listed
    r2 = _runner.invoke(app, ["model", "list", "--json"])
    assert r2.exit_code == 0, r2.output
    data = json.loads(r2.output)
    assert len(data["models"]) == 1
    assert data["models"][0]["display_name"] == "MyClaude"

    # Chat should now work
    r3 = _runner.invoke(app, ["chat", "-m", "hello"])
    assert r3.exit_code == 0, r3.output
    assert "Hello from agent!" in r3.output
