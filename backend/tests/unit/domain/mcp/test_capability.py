# backend/tests/unit/domain/mcp/test_capability.py
from datetime import UTC, datetime

from coffer.domain.mcp.capability import (
    MCPCapabilityPreference,
    MCPInvocation,
    MCPPrompt,
    MCPPromptArgument,
    MCPResource,
    MCPTool,
)


def test_mcp_tool_minimal():
    t = MCPTool(name="read_file", description=None, input_schema={"type": "object"})
    assert t.name == "read_file"
    assert t.input_schema == {"type": "object"}


def test_mcp_resource_minimal():
    r = MCPResource(uri="file:///tmp/x.txt", name=None, description=None, mime_type=None)
    assert r.uri == "file:///tmp/x.txt"


def test_mcp_prompt_with_arguments():
    p = MCPPrompt(
        name="summarize",
        description="summarise something",
        arguments=[MCPPromptArgument(name="text", description=None, required=True)],
    )
    assert p.arguments[0].name == "text"
    assert p.arguments[0].required is True


def test_mcp_capability_preference_minimal():
    pref = MCPCapabilityPreference(
        id=None,
        resource_id=42,
        capability_type="tool",
        capability_key="read_file",
        enabled=True,
        first_seen_at=datetime(2026, 5, 20, tzinfo=UTC),
        last_seen_at=datetime(2026, 5, 20, tzinfo=UTC),
    )
    assert pref.id is None
    assert pref.capability_type == "tool"


def test_mcp_invocation_minimal():
    inv = MCPInvocation(
        id=None,
        timestamp=datetime(2026, 5, 20, tzinfo=UTC),
        resource_name="filesystem",
        capability_type="tool",
        capability_key="read_file",
        duration_ms=42,
        status="ok",
        error_message=None,
        session_id="sess-xyz",
    )
    assert inv.duration_ms == 42
    assert inv.status == "ok"
