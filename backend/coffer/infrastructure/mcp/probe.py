"""Test one MCP server: start or reach it, initialize, list its tools, close.

Spec mcp-gateway "Test an unsaved server config before adding it" and "Report what
a test of a registered server found". One probe serves both: the caller supplies the
transport, the secret overlay it may release (typed values for an unsaved
config, the materialised binding for a registered server), and — for a URL the
person typed — the SSRF guard. The probe persists nothing; what to record
afterwards is the caller's decision.

**stdio.** The server runs under ``/bin/sh`` so that, when it exits by itself,
its exit status reaches the result: the wrapper waits for it and prints
:data:`~coffer.domain.mcp.probe.EXIT_MARKER` on stderr (the SDK hides the
process object). stderr goes to a private temporary file, never to the
server's log, and is read back as a redacted tail. The connection is asked to
stop the whole process group on close (``kill_group_on_close``), so a
grandchild the server forked cannot outlive the test — on success, failure,
the time limit, or the caller being cancelled.

**HTTP.** The URL passes ``url_guard`` (off the event loop) before any request.
The SDK follows a redirect only within the endpoint's own origin
(``mcp.shared._httpx_utils.stream_within_origin``), so a redirect cannot carry
the test to a host the guard did not see.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

from mcp.client.stdio import get_default_environment

from coffer.domain.errors import UpstreamTimeout
from coffer.domain.mcp.probe import (
    EXIT_MARKER,
    PROBE_TOTAL_SECONDS,
    ProbeErrorCode,
    ProbeResult,
    ProbeTool,
    redact,
    stderr_tail,
)
from coffer.domain.mcp.server_config import HttpTransport, StdioTransport
from coffer.infrastructure.mcp.http_client import HttpUpstreamConnection, _leaf_exception
from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection
from coffer.infrastructure.platform.host import HostOs, host_os

#: Raises ``ValueError`` for a URL that must not be requested.
UrlGuard = Callable[[str], object]

_SH = "/bin/sh"
#: ``"$0" "$@"`` runs the server with its own argv; the status follows on stderr.
_WRAPPER = '"$0" "$@"; c=$?; printf "\\n%s%d\\n" "' + EXIT_MARKER + '" "$c" >&2; exit "$c"'


class _FailError(Exception):
    def __init__(self, code: ProbeErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _launcher_problem(transport: StdioTransport, env: Mapping[str, str]) -> str | None:
    """Why the process cannot start at all, found before starting it."""
    if transport.cwd and not Path(transport.cwd).expanduser().is_dir():
        return f"The working directory {transport.cwd} does not exist."
    command = transport.command
    if os.sep in command or (os.altsep and os.altsep in command):
        if not os.access(os.path.expanduser(command), os.X_OK):
            return f"{command} does not exist or is not executable."
        return None
    if shutil.which(command, path=env.get("PATH")) is None:
        return f"The command {command!r} was not found on PATH."
    return None


async def _list(conn: Any, method: str) -> Any:
    return await conn.request(method, {})


async def _inventory(
    conn: Any, caps: Mapping[str, Any]
) -> tuple[tuple[ProbeTool, ...], int | None, int | None]:
    """tools/list, and the resource and prompt counts when the server declares them."""
    listed = await _list(conn, "tools/list")
    tools = tuple(
        ProbeTool(name=t.name, description=getattr(t, "description", None))
        for t in getattr(listed, "tools", [])
    )
    resources: int | None = None
    prompts: int | None = None
    if caps.get("resources"):
        try:
            resources = len((await _list(conn, "resources/list")).resources)
        except Exception:
            resources = None
    if caps.get("prompts"):
        try:
            prompts = len((await _list(conn, "prompts/list")).prompts)
        except Exception:
            prompts = None
    return tools, resources, prompts


def _http_failure(exc: BaseException, url: str, answered: int | None = None) -> _FailError:
    """Classify a failed HTTP connect/initialize without echoing the URL's query."""
    if isinstance(exc, UpstreamTimeout):
        return _FailError("timeout", "The server did not answer within the time limit.")
    cause = _leaf_exception(exc.__cause__ or exc)
    host = urlparse(url).hostname or url
    response = getattr(cause, "response", None)
    status = getattr(response, "status_code", None) or answered
    if status in (401, 403):
        return _FailError("auth_rejected", f"{host} rejected the credentials (HTTP {status}).")
    if status is not None:
        return _FailError("initialize_failed", f"{host} answered HTTP {status}.")
    name = type(cause).__name__
    if "Connect" in name or isinstance(cause, OSError):
        return _FailError("connect_failed", f"Could not connect to {host} ({name}).")
    return _FailError("initialize_failed", f"{host} did not complete MCP initialize ({name}).")


async def _probe_http(
    transport: HttpTransport,
    overlay: dict[str, str],
    *,
    spawn_timeout: int,
    request_timeout: int,
    server_name: str,
    url_guard: UrlGuard | None,
) -> tuple[dict[str, Any], tuple[ProbeTool, ...], int | None, int | None]:
    url = str(transport.url)
    if url_guard is not None:
        try:
            await asyncio.to_thread(url_guard, url)
        except ValueError as exc:
            host = urlparse(url).hostname or url
            raise _FailError(
                "url_refused",
                f"{host} is a loopback, private or link-local address, so it is not "
                "requested from a config that is not saved; a server there is tested "
                "once it is added.",
            ) from exc
    conn = HttpUpstreamConnection(
        transport=transport,
        header_overlay=overlay,
        spawn_timeout_seconds=spawn_timeout,
        request_timeout_seconds=request_timeout,
        server_name=server_name,
    )
    try:
        try:
            caps = await conn.spawn_and_initialize()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise _http_failure(exc, url, conn.first_error_status) from exc
        try:
            tools, resources, prompts = await _inventory(conn, caps)
        except UpstreamTimeout as exc:
            raise _FailError("timeout", "The server did not list its tools in time.") from exc
        except Exception as exc:
            raise _FailError(
                "initialize_failed", f"tools/list failed ({type(exc).__name__})."
            ) from exc
        return caps, tools, resources, prompts
    finally:
        await conn.close()


async def _probe_stdio(
    transport: StdioTransport,
    overlay: dict[str, str],
    sink: TextIO,
    *,
    spawn_timeout: int,
    request_timeout: int,
    server_name: str,
    server_uid: str,
) -> tuple[dict[str, Any], tuple[ProbeTool, ...], int | None, int | None]:
    env = {**get_default_environment(), **transport.env, **overlay}
    problem = _launcher_problem(transport, env)
    if problem is not None:
        raise _FailError("spawn_failed", problem)
    wrapped = transport
    if host_os() is not HostOs.WINDOWS and Path(_SH).exists():
        wrapped = transport.model_copy(
            update={"command": _SH, "args": ["-c", _WRAPPER, transport.command, *transport.args]}
        )
    conn = StdioUpstreamConnection(
        transport=wrapped,
        env_overlay=overlay,
        spawn_timeout_seconds=spawn_timeout,
        request_timeout_seconds=request_timeout,
        server_name=server_name,
        server_uid=server_uid,
        stderr_sink=sink,
        kill_group_on_close=True,
    )
    try:
        try:
            caps = await conn.spawn_and_initialize()
        except UpstreamTimeout as exc:
            raise _FailError("timeout", "The server did not finish starting in time.") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            cause = exc.__cause__
            if isinstance(cause, (FileNotFoundError, PermissionError)):
                raise _FailError("spawn_failed", "The process could not be started.") from exc
            raise _FailError(
                "initialize_failed", "The server did not complete MCP initialize."
            ) from exc
        try:
            tools, resources, prompts = await _inventory(conn, caps)
        except UpstreamTimeout as exc:
            raise _FailError("timeout", "The server did not list its tools in time.") from exc
        except Exception as exc:
            raise _FailError(
                "initialize_failed", f"tools/list failed ({type(exc).__name__})."
            ) from exc
        return caps, tools, resources, prompts
    finally:
        await conn.close()


def _read(sink: TextIO) -> str:
    try:
        sink.flush()
        sink.seek(0)
        return sink.read()
    except (OSError, ValueError):
        return ""


async def probe_server(
    transport: StdioTransport | HttpTransport,
    overlay: Mapping[str, str],
    *,
    spawn_timeout_seconds: int,
    request_timeout_seconds: int,
    secrets: Iterable[str] = (),
    server_name: str = "test",
    server_uid: str = "",
    url_guard: UrlGuard | None = None,
    total_seconds: float | None = None,
) -> ProbeResult:
    """Test one server within ``total_seconds``; never raises for a server's
    failure (only for the caller's own cancellation)."""
    # Read at call time so a test can shorten the limit on the module.
    if total_seconds is None:
        total_seconds = PROBE_TOTAL_SECONDS
    secret_list = [*secrets, *overlay.values()]
    spawn = max(1, min(spawn_timeout_seconds, int(total_seconds)))
    request = max(1, min(request_timeout_seconds, int(total_seconds)))
    start = time.monotonic()
    sink = tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace")  # noqa: SIM115
    failure: _FailError | None = None
    outcome: tuple[dict[str, Any], tuple[ProbeTool, ...], int | None, int | None] | None = None
    try:
        try:
            async with asyncio.timeout(total_seconds):
                if isinstance(transport, StdioTransport):
                    outcome = await _probe_stdio(
                        transport,
                        dict(overlay),
                        sink,
                        spawn_timeout=spawn,
                        request_timeout=request,
                        server_name=server_name,
                        server_uid=server_uid,
                    )
                else:
                    outcome = await _probe_http(
                        transport,
                        dict(overlay),
                        spawn_timeout=spawn,
                        request_timeout=request,
                        server_name=server_name,
                        url_guard=url_guard,
                    )
        except TimeoutError:
            failure = _FailError("timeout", f"The test ran past its {int(total_seconds)} s limit.")
        except _FailError as f:
            failure = f
        latency = _elapsed_ms(start)
        tail, exit_code = stderr_tail(_read(sink), secret_list)
    finally:
        sink.close()
    if failure is None and outcome is not None:
        caps, tools, resources, prompts = outcome
        return ProbeResult(
            ok=True,
            latency_ms=latency,
            tools=tools,
            resource_count=resources,
            prompt_count=prompts,
            protocol_version="2025-06-18",
            server_capabilities=caps,
            stderr_tail=tail,
        )
    assert failure is not None
    code: ProbeErrorCode = failure.code
    message = failure.message
    if exit_code is not None and code in ("initialize_failed", "timeout"):
        code = "exited"
        message = f"The process exited with code {exit_code}."
    return ProbeResult(
        ok=False,
        latency_ms=latency,
        error_code=code,
        error_message=redact(message, secret_list),
        exit_code=exit_code if code == "exited" else None,
        stderr_tail=tail,
    )


__all__ = ["UrlGuard", "probe_server"]
