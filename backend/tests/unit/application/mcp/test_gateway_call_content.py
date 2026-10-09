"""What a call's row records of its content (spec mcp-gateway "Record
invocations with redacted, bounded content")."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.mcp import call_content
from coffer.application.mcp.call_content import CallContentRecording, publish_exchange
from coffer.application.mcp.gateway_handlers import handle_tools_call
from coffer.domain.activity_content import MASK
from coffer.domain.errors import ToolDisabled
from coffer.domain.mcp.capability import MCPCapabilityPreference, MCPInvocation
from coffer.domain.resource import Resource

INJECTED = "ghp_injected_value_0123456789"


class _Resources:
    async def get_by_name(self, kind: str, name: str) -> Resource:
        now = datetime.now(tz=UTC)
        return Resource(
            uid="0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            kind="mcp_server",
            name="fs",
            description=None,
            config={},
            enabled=True,
            created_at=now,
            updated_at=now,
        )


class _Prefs:
    def __init__(self, *, disabled: bool = False) -> None:
        self._disabled = disabled

    async def find(self, uid: str, ctype: str, key: str) -> MCPCapabilityPreference | None:
        if not self._disabled:
            return None
        now = datetime.now(tz=UTC)
        return MCPCapabilityPreference(uid, ctype, key, False, now, now)  # type: ignore[arg-type]


class _Invocations:
    def __init__(self) -> None:
        self.rows: list[MCPInvocation] = []

    async def insert(self, inv: MCPInvocation) -> None:
        self.rows.append(inv)


class _Conn:
    def __init__(self, answer: Any = None, raises: BaseException | None = None) -> None:
        self._answer, self._raises = answer, raises

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        if self._raises is not None:
            raise self._raises
        return self._answer


class _Supervisor:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def mask_values(self, name: str) -> tuple[str, ...]:
        return (INJECTED,)

    async def get_or_spawn(self, name: str) -> Any:
        return self._conn

    async def evict(self, name: str) -> None:
        return None


class _Store:
    def __init__(self, value: bool | None) -> None:
        self.value = value

    def read(self) -> bool | None:
        return self.value

    def write(self, enabled: bool) -> None:
        self.value = enabled


@pytest.fixture(autouse=True)
def _recording_on() -> Iterator[None]:
    call_content.configure(CallContentRecording(_Store(None)))
    yield
    call_content.configure(None)


async def _call(conn: Any, *, prefs: _Prefs | None = None, arguments: Any = None) -> _Invocations:
    inv = _Invocations()

    async def _noop(_name: str) -> None:
        return None

    with contextlib.suppress(Exception):
        await handle_tools_call(
            {"name": "fs__read", "arguments": arguments or {"path": "/notes"}},
            resources=_Resources(),
            supervisor=_Supervisor(conn),
            prefs=prefs or _Prefs(),
            invocations=inv,
            session_id="s1",
            clock=lambda: datetime.now(tz=UTC),
            ensure_subscribed=_noop,
        )
    return inv


def _part(row: MCPInvocation, name: str) -> Any:
    assert row.content is not None
    return json.loads(row.content[name]["text"])


@pytest.mark.asyncio
async def test_a_call_records_its_arguments_and_result() -> None:
    answer = {"content": [{"type": "text", "text": "hello"}]}
    [row] = (await _call(_Conn(answer))).rows
    assert _part(row, "arguments") == {"path": "/notes"}
    assert _part(row, "result")["content"][0]["text"] == "hello"
    assert "error" not in (row.content or {})


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an injected secret echoed by the upstream is masked in the record"
)
@pytest.mark.asyncio
async def test_an_injected_value_echoed_back_is_masked() -> None:
    ok = (await _call(_Conn({"content": [{"type": "text", "text": f"key={INJECTED}"}]}))).rows
    failed = (await _call(_Conn(raises=RuntimeError(f"auth failed for {INJECTED}")))).rows
    for row in (*ok, *failed):
        assert INJECTED not in json.dumps(row.content)
        assert INJECTED not in (row.error_message or "")
    assert MASK in _part(ok[0], "result")["content"][0]["text"]
    assert _part(failed[0], "error") == f"RuntimeError: auth failed for {MASK}"


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a refused call records its arguments only")
@pytest.mark.asyncio
async def test_a_refused_call_records_its_arguments_only() -> None:
    [row] = (await _call(_Conn({}), prefs=_Prefs(disabled=True))).rows
    assert row.status == "denied"
    assert set(row.content or {}) == {"arguments"}


@pytest.mark.asyncio
async def test_recording_off_records_no_content() -> None:
    call_content.configure(CallContentRecording(_Store(False)))
    [row] = (await _call(_Conn({"content": []}))).rows
    assert row.content is None and row.status == "ok"


@pytest.mark.asyncio
async def test_a_connection_publishes_its_http_exchange_into_the_row() -> None:
    class _HttpConn:
        async def request(self, method: str, params: dict[str, Any]) -> Any:
            publish_exchange(
                request={"method": "GET", "url": "https://x/y", "headers": {"Authorization": "t"}},
                response={"status": 200, "headers": {"x-sp-error": "101"}, "body": None},
            )
            return {"content": [], "isError": False}

    [row] = (await _call(_HttpConn())).rows
    assert _part(row, "request")["headers"] == {"Authorization": MASK}
    assert _part(row, "response") == {"status": 200, "headers": {"x-sp-error": "101"}, "body": None}


def test_a_switch_writes_before_it_holds() -> None:
    store = _Store(None)
    recording = CallContentRecording(store)
    assert recording.enabled is True
    assert recording.set(False) is True
    assert store.value is False and recording.enabled is False


async def test_tool_disabled_is_raised_for_a_refused_call() -> None:
    inv = _Invocations()

    async def _noop(_name: str) -> None:
        return None

    with pytest.raises(ToolDisabled):
        await handle_tools_call(
            {"name": "fs__read", "arguments": {}},
            resources=_Resources(),
            supervisor=_Supervisor(_Conn({})),
            prefs=_Prefs(disabled=True),
            invocations=inv,
            session_id="s1",
            clock=lambda: datetime.now(tz=UTC),
            ensure_subscribed=_noop,
        )
