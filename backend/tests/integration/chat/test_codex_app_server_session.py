"""Integration test for the Codex app-server subprocess seam (spec 008, T2).

The real-subprocess factory is exercised here, NOT in the unit tier (unit tests
must stay pure). The whole module is skipped when ``codex`` is absent so CI
without the binary stays green; a fuller real-binary canary (handshake +
NDJSON framing) comes in a later task.
"""

from __future__ import annotations

import shutil

import pytest

from coffer.infrastructure.chat.codex_app_server import (
    CodexSubprocessSession,
    default_app_server_session,
)

pytestmark = pytest.mark.skipif(shutil.which("codex") is None, reason="codex binary not installed")


def test_factory_builds_a_session_object(tmp_path) -> None:
    session = default_app_server_session(str(tmp_path), env=None)
    assert isinstance(session, CodexSubprocessSession)
    # Not started yet — touching ``rpc`` must fail loudly rather than return a
    # half-built client.
    with pytest.raises(RuntimeError):
        _ = session.rpc
