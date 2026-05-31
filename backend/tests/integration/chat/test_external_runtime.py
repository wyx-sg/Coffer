"""ExternalAgentRuntime against a real stub subprocess (spec 008)."""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.chat.runtime import ChatTurnRequest, DoneEvent, ErrorEvent, TextDelta
from coffer.infrastructure.chat import external_runtime
from coffer.infrastructure.chat.external_runtime import ExternalAgentRuntime

SPEC = "008-builtin-agent-chat"


def _stub_agent(tmp_path: pathlib.Path) -> pathlib.Path:
    """A tiny executable standing in for `claude`: emits two stream-json text
    lines then exits 0."""
    path = tmp_path / "stub-agent"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        'print(\'{"type":"text","text":"Hello from "}\')\n'
        'print(\'{"type":"text","text":"the stub agent"}\')\n'
        "sys.exit(0)\n"
    )
    path.chmod(0o755)
    return path


async def _drain(rt: ExternalAgentRuntime, req: ChatTurnRequest):
    return [ev async for ev in rt.stream(req)]


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat",
    scenario="chat with an external agent streams its subprocess output",
)
async def test_external_agent_streams_subprocess_output(tmp_path, monkeypatch):
    stub = _stub_agent(tmp_path)
    monkeypatch.setenv("COFFER_CHAT_BIN_CLAUDE_CODE", str(stub))
    rt = ExternalAgentRuntime(config={"type": "claude_code"})
    events = await _drain(rt, ChatTurnRequest(history=[], user_message="hi"))
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "Hello from the stub agent"
    assert isinstance(events[-1], DoneEvent)
    # No orphan: the child has been reaped (return code recorded).
    assert rt._proc is not None and rt._proc.returncode is not None


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat",
    scenario="external agent binary missing is surfaced as a clear error",
)
async def test_external_agent_missing_binary_errors(tmp_path, monkeypatch):
    monkeypatch.delenv("COFFER_CHAT_BIN_CLAUDE_CODE", raising=False)
    monkeypatch.setattr(external_runtime.shutil, "which", lambda _name: None)
    rt = ExternalAgentRuntime(config={"type": "claude_code"})
    events = await _drain(rt, ChatTurnRequest(history=[], user_message="hi"))
    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert "claude_code" in events[0].message
    # Nothing was spawned, so there is nothing to orphan.
    assert rt._proc is None


async def test_nonzero_exit_surfaces_error(tmp_path, monkeypatch):
    failing = tmp_path / "failing-agent"
    failing.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(2)\n")
    failing.chmod(0o755)
    monkeypatch.setenv("COFFER_CHAT_BIN_CODEX", str(failing))
    rt = ExternalAgentRuntime(config={"type": "codex"})
    events = await _drain(rt, ChatTurnRequest(history=[], user_message="hi"))
    assert any(isinstance(e, ErrorEvent) for e in events)
    assert not any(isinstance(e, DoneEvent) for e in events)
