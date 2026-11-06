"""The SDK's warning for a session the upstream already forgot is dropped."""

from __future__ import annotations

import logging

import pytest

from coffer.infrastructure.logging.setup import _install_sdk_noise_filter


def test_a_404_on_session_termination_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    _install_sdk_noise_filter()
    _install_sdk_noise_filter()  # idempotent
    sdk = logging.getLogger("mcp.client.streamable_http")
    assert sum(type(f).__name__ == "_GoneSessionFilter" for f in sdk.filters) == 1
    with caplog.at_level(logging.WARNING, logger="mcp.client.streamable_http"):
        sdk.warning("Session termination failed: 404")
        sdk.warning("Session termination failed: 500")
    assert [r.getMessage() for r in caplog.records] == ["Session termination failed: 500"]
