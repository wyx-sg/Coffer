"""Unit tests for gateway_handlers helpers.

Covers the SC-010-adjacent contract: arbitrary upstream exception text must
not leak into the invocation log via str(e). Coffer-internal errors (whose
text is authored by us) are still preserved for debuggability.
"""

from __future__ import annotations

from coffer.application.mcp.gateway_handlers import _safe_error_summary
from coffer.domain.errors import (
    ResourceNotFound,
    ToolDisabled,
    UpstreamTimeout,
    UpstreamUnavailable,
)

SENTINEL = "COFFER_LEAK_SENTINEL_abc123xyz"


def test_arbitrary_exception_message_is_not_persisted() -> None:
    """A non-CofferError exception (e.g., bubbled up from the MCP SDK) might
    carry upstream-controlled text — including credentials echoed back by a
    misbehaving server. _safe_error_summary must drop the message and keep
    only the class name so the invocation log stays clean.
    """
    summary = _safe_error_summary(RuntimeError(f"auth failed: token={SENTINEL}"))
    assert SENTINEL not in summary
    assert summary == "RuntimeError"


def test_value_error_message_is_not_persisted() -> None:
    summary = _safe_error_summary(ValueError(f"bad input contains {SENTINEL}"))
    assert SENTINEL not in summary
    assert summary == "ValueError"


def test_coffer_internal_errors_keep_their_message() -> None:
    """CofferError text is authored by Coffer code, never by upstream — so
    it's safe (and useful) to keep."""
    summary = _safe_error_summary(UpstreamTimeout("upstream 'fs' did not respond in 30s"))
    assert "UpstreamTimeout" in summary
    assert "did not respond" in summary


def test_resource_not_found_keeps_message() -> None:
    summary = _safe_error_summary(ResourceNotFound("mcp_server", "ghost"))
    assert "ResourceNotFound" in summary
    assert "ghost" in summary


def test_upstream_unavailable_keeps_message() -> None:
    summary = _safe_error_summary(UpstreamUnavailable("'fs' is in cooldown until 2026-01-01"))
    assert "UpstreamUnavailable" in summary
    assert "cooldown" in summary


def test_tool_disabled_keeps_message() -> None:
    summary = _safe_error_summary(ToolDisabled("tool:'write_file' is disabled"))
    assert "ToolDisabled" in summary
    assert "write_file" in summary
