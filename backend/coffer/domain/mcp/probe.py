"""The vocabulary of a one-off MCP server test, and its pure text rules.

A *probe* starts a server for the length of one test (or connects to an HTTP
one), runs ``initialize`` and ``tools/list``, keeps the tail of what the server
printed on stderr, and closes everything again (spec mcp-gateway "Test an
unsaved server config before adding it"). Both the Add dialog's test of a config
that is not saved and the test of a registered server report the same
:class:`ProbeResult`.

Nothing a person typed as a secret may leave a probe: every line of stderr and
the error message pass through :func:`redact` with the probe's secret values
before they are returned. No I/O here.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

#: Why a probe failed, as a stable machine code the UI words.
ProbeErrorCode = Literal[
    # The typed URL resolves to a loopback, private or link-local host.
    "url_refused",
    # The process could not be started (command not on PATH, cwd missing).
    "spawn_failed",
    # The process started and exited before the test finished.
    "exited",
    # The whole test ran past its time limit.
    "timeout",
    # The server answered, but MCP initialize or tools/list failed.
    "initialize_failed",
    # The HTTP server could not be reached.
    "connect_failed",
    # The config cites a stored secret, which is released only to a server
    # whose binding a person approved.
    "stored_secret_not_released",
    # A transport a probe does not open (a custom-tool group).
    "unsupported_transport",
]

#: The longest test there is, whatever the config's own timeouts say.
PROBE_TOTAL_SECONDS = 30.0
#: How many stderr lines a result keeps (the newest).
STDERR_TAIL_LINES = 20
#: A stderr line longer than this is cut, so one runaway line cannot bloat a result.
STDERR_LINE_MAX = 400
#: What a redacted secret reads as.
REDACTED = "••••••"
#: A value this short is not redacted inside other text: replacing every "1"
#: or "on" would make the tail unreadable without protecting anything.
_MIN_SECRET_LEN = 4

#: The marker the stdio probe's wrapper prints on stderr once the server's
#: process has exited, followed by its exit status. Stripped from the tail.
EXIT_MARKER = "__coffer_probe_exit__="
_EXIT_RE = re.compile(re.escape(EXIT_MARKER) + r"(\d+)\s*$")
#: A key name that looks like it holds a secret (the adopt-time pattern the
#: agent kind uses for config-file entries, restated for this kind).
_SECRET_KEY_RE = re.compile(
    r"(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|CREDENTIAL|AUTHORIZATION)", re.IGNORECASE
)


@dataclass(frozen=True)
class ProbeTool:
    name: str
    description: str | None


@dataclass(frozen=True)
class ProbeResult:
    """What one test found. ``ok`` is true exactly when ``error_code`` is None."""

    ok: bool
    latency_ms: int
    tools: tuple[ProbeTool, ...] = ()
    resource_count: int | None = None
    prompt_count: int | None = None
    protocol_version: str | None = None
    server_capabilities: Mapping[str, object] | None = None
    error_code: ProbeErrorCode | None = None
    error_message: str | None = None
    exit_code: int | None = None
    stderr_tail: tuple[str, ...] = field(default_factory=tuple)

    @property
    def tool_count(self) -> int:
        return len(self.tools)


def secret_looking(values: Mapping[str, str]) -> list[str]:
    """The values of the keys whose names look like they hold a secret."""
    return [v for k, v in values.items() if v and _SECRET_KEY_RE.search(k)]


def secret_values(values: Iterable[str]) -> tuple[str, ...]:
    """The values worth redacting, longest first (so a secret that contains
    another is replaced whole)."""
    unique = {v for v in values if v and len(v) >= _MIN_SECRET_LEN}
    return tuple(sorted(unique, key=len, reverse=True))


def redact(text: str, secrets: Iterable[str]) -> str:
    """``text`` with every secret value replaced by :data:`REDACTED`."""
    for value in secret_values(secrets):
        text = text.replace(value, REDACTED)
    return text


def stderr_tail(
    raw: str, secrets: Iterable[str], *, limit: int = STDERR_TAIL_LINES
) -> tuple[tuple[str, ...], int | None]:
    """The newest ``limit`` non-empty stderr lines, redacted and cut to
    :data:`STDERR_LINE_MAX`, and the exit status the wrapper's marker line
    reported (``None`` when the process had not exited on its own)."""
    exit_code: int | None = None
    lines: list[str] = []
    for line in raw.splitlines():
        m = _EXIT_RE.search(line)
        if m is not None:
            exit_code = int(m.group(1))
            line = line[: m.start()]
        line = line.rstrip()
        if line:
            lines.append(line)
    kept = [redact(line, secrets)[:STDERR_LINE_MAX] for line in lines[-limit:]]
    return tuple(kept), exit_code


__all__ = [
    "EXIT_MARKER",
    "PROBE_TOTAL_SECONDS",
    "REDACTED",
    "STDERR_LINE_MAX",
    "STDERR_TAIL_LINES",
    "ProbeErrorCode",
    "ProbeResult",
    "ProbeTool",
    "redact",
    "secret_looking",
    "secret_values",
    "stderr_tail",
]
