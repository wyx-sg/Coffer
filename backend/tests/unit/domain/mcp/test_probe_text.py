"""The MCP server test's pure text rules: redaction and the stderr tail."""

from __future__ import annotations

from coffer.domain.mcp.probe import (
    EXIT_MARKER,
    REDACTED,
    ProbeResult,
    ProbeTool,
    redact,
    secret_looking,
    secret_values,
    stderr_tail,
)


def test_secret_values_drops_short_and_empty_values_longest_first() -> None:
    assert secret_values(["abcd", "", "ab", "abcdefgh", "abcd"]) == ("abcdefgh", "abcd")


def test_redact_replaces_the_longest_secret_whole() -> None:
    assert redact("key=abcdefgh", ["abcd", "abcdefgh"]) == f"key={REDACTED}"


def test_secret_looking_reads_key_names() -> None:
    assert secret_looking({"API_KEY": "v1", "LOG": "debug", "X_TOKEN": ""}) == ["v1"]


def test_stderr_tail_keeps_the_newest_lines_redacted_and_reads_the_exit_marker() -> None:
    raw = "\n".join(f"line {i} tok-9999" for i in range(30)) + f"\n\n{EXIT_MARKER}7\n"
    tail, code = stderr_tail(raw, ["tok-9999"])
    assert code == 7
    assert len(tail) == 20
    assert tail[0] == f"line 10 {REDACTED}"
    assert tail[-1] == f"line 29 {REDACTED}"


def test_stderr_tail_without_a_marker_has_no_exit_code() -> None:
    assert stderr_tail("booting\n", []) == (("booting",), None)


def test_a_marker_after_text_on_the_same_line_is_stripped() -> None:
    tail, code = stderr_tail(f"no newline{EXIT_MARKER}1", [])
    assert (tail, code) == (("no newline",), 1)


def test_tool_count_is_the_number_of_tools() -> None:
    result = ProbeResult(ok=True, latency_ms=1, tools=(ProbeTool("a", None), ProbeTool("b", "x")))
    assert result.tool_count == 2
