"""``failure_reason``: a failed test's error code as the reason stored with the failing state."""

from __future__ import annotations

import pytest

from coffer.domain.mcp.probe import failure_reason


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a failed test's error code maps to a reason")
def test_error_codes_map_to_reasons() -> None:
    assert failure_reason("auth_rejected") == "auth_rejected"
    assert failure_reason("connect_failed") == "unreachable"
    assert failure_reason("timeout") == "unreachable"
    assert failure_reason("spawn_failed") == "command_not_found"
    for other in ("exited", "initialize_failed", "url_refused", None):
        assert failure_reason(other) == "other"  # type: ignore[arg-type]
