"""Official quota reports flow from driven agents; the Codex reader asks app-server."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import RateLimitEvent, ResultMessage
from claude_agent_sdk.types import RateLimitInfo

from coffer.domain.chat.events import TurnDone
from coffer.infrastructure.chat.claude_sdk_agent import ClaudeSdkAgentAdapter
from coffer.infrastructure.chat.codex_agent import CodexAppServerAdapter
from coffer.infrastructure.chat.codex_rate_limits import AppServerRateLimitReader
from tests.integration.chat.test_claude_sdk_agent import _Factory as _SdkFactory
from tests.integration.chat.test_claude_sdk_agent import _user_turn
from tests.integration.chat.test_codex_app_server_agent import (
    FakeCodexAppServer,
    _Factory,
    _Frame,
)

_RAW = {
    "status": "allowed",
    "rateLimitType": "five_hour",
    "utilization": 0.4,
    "unifiedWindows": {"five_hour": {"utilization": 0.4, "resetsAt": 1790000000}},
}
_CODEX_LIMITS = {
    "rateLimits": {"primary": {"usedPercent": 22, "windowDurationMins": 300, "resetsAt": 1}}
}


async def _noop(_: str) -> None:
    return None


def _result() -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s1",
        usage={"input_tokens": 1, "output_tokens": 1},
        total_cost_usd=0.0,
    )


def _rate_limit_event() -> RateLimitEvent:
    info = RateLimitInfo(status="allowed", utilization=0.4, raw=_RAW)
    return RateLimitEvent(rate_limit_info=info, uuid="u1", session_id="s1")


async def _drain(adapter: Any) -> list[Any]:
    stream = await adapter.run_turn(history=_user_turn("hi"))
    return [e async for e in stream]


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="Claude Code quota comes from a driven session's rate-limit event",
)
async def test_claude_rate_limit_event_reaches_the_observer() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []

    async def observe(agent: str, payload: dict[str, Any]) -> None:
        seen.append((agent, payload))

    adapter = ClaudeSdkAgentAdapter(
        cwd="/tmp",
        resume_session=None,
        extra={},
        on_session=_noop,
        session_factory=_SdkFactory([_rate_limit_event(), _result()]),
        observe_quota=observe,
    )
    events = await _drain(adapter)
    assert seen == [("claude_code", _RAW)]
    assert isinstance(events[-1], TurnDone)


async def test_a_failing_observer_never_affects_the_turn() -> None:
    async def broken(agent: str, payload: dict[str, Any]) -> None:
        raise RuntimeError("db locked")

    adapter = ClaudeSdkAgentAdapter(
        cwd="/tmp",
        resume_session=None,
        extra={},
        on_session=_noop,
        session_factory=_SdkFactory([_rate_limit_event(), _result()]),
        observe_quota=broken,
    )
    assert isinstance((await _drain(adapter))[-1], TurnDone)


async def test_codex_rate_limits_updated_notification_reaches_the_observer() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []

    async def observe(agent: str, payload: dict[str, Any]) -> None:
        seen.append((agent, payload))

    server = FakeCodexAppServer(
        frames=[
            _Frame("turn/start", "account/rateLimits/updated", _CODEX_LIMITS),
            _Frame(
                "turn/start",
                "turn/completed",
                {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"}},
            ),
        ]
    )
    adapter = CodexAppServerAdapter(
        cwd="/tmp",
        resume_session=None,
        extra={},
        session_factory=_Factory(server),
        on_session=_noop,
        observe_quota=observe,
    )
    stream = await adapter.run_turn(history=_user_turn("hi"))
    events = await asyncio.wait_for(_collect(stream), timeout=5)
    assert seen == [("codex", _CODEX_LIMITS)]
    assert isinstance(events[-1], TurnDone)


async def _collect(stream: Any) -> list[Any]:
    return [e async for e in stream]


class _RateLimitServer(FakeCodexAppServer):
    """Answers ``account/rateLimits/read`` (or refuses it, like a non-ChatGPT login)."""

    def __init__(self, *, signed_in: bool) -> None:
        super().__init__(fail_methods=set() if signed_in else {"account/rateLimits/read"})
        self.signed_in = signed_in

    async def _handle_client_request(
        self, method: str, req_id: int, params: dict[str, Any]
    ) -> None:
        if method == "account/rateLimits/read" and self.signed_in:
            self.requests.append((method, params))
            await self._send({"jsonrpc": "2.0", "id": req_id, "result": _CODEX_LIMITS})
            return
        await super()._handle_client_request(method, req_id, params)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="Codex quota comes from its app-server",
)
async def test_codex_reader_handshakes_then_reads_rate_limits() -> None:
    server = _RateLimitServer(signed_in=True)
    factory = _Factory(server)
    result = await AppServerRateLimitReader(session_factory=factory).read()
    assert result == _CODEX_LIMITS
    assert [m for m, _ in server.requests] == ["initialize", "account/rateLimits/read"]
    assert factory.session is not None and factory.session.closed


async def test_codex_reader_returns_none_when_not_signed_in_or_absent() -> None:
    server = _RateLimitServer(signed_in=False)
    assert await AppServerRateLimitReader(session_factory=_Factory(server)).read() is None

    def absent(cwd: str, env: dict[str, str] | None) -> Any:
        raise RuntimeError("codex binary not found on PATH")

    assert await AppServerRateLimitReader(session_factory=absent).read() is None


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed")
async def test_real_codex_with_an_empty_home_has_no_subscription(tmp_path: Path) -> None:
    """The real binary against a throwaway CODEX_HOME (never ~/.codex): not
    signed in, so there is nothing official to show."""
    home = tmp_path / "codex-home"
    home.mkdir()

    async def env() -> dict[str, str]:
        return {"CODEX_HOME": str(home)}

    reader = AppServerRateLimitReader(resolve_env=env, cwd=str(tmp_path), timeout=30)
    assert await reader.read() is None
