# backend/tests/unit/domain/mcp/test_capability.py
import dataclasses
from datetime import UTC, datetime

from coffer.domain.mcp.capability import (
    MCPInvocation,
    MCPPrompt,
    MCPPromptArgument,
    MCPResource,
    MCPTool,
)


def test_mcp_tool_defaults_description_to_none_when_omitted():
    # Omit the optional field so the model's DEFAULT is exercised (not an
    # echoed literal). A regression dropping `description: ... = None` fails here.
    t = MCPTool(name="read_file", input_schema={"type": "object"})
    assert t.name == "read_file"
    assert t.input_schema == {"type": "object"}
    assert t.description is None


def test_mcp_resource_optional_fields_default_to_none_when_omitted():
    r = MCPResource(uri="file:///tmp/x.txt")
    assert r.uri == "file:///tmp/x.txt"
    assert r.name is None
    assert r.description is None
    assert r.mime_type is None


def test_mcp_prompt_arguments_default_empty_and_required_defaults_false():
    # Default empty arg list on the prompt, and default required=False on an arg.
    p = MCPPrompt(name="bare")
    assert p.arguments == []
    assert MCPPromptArgument(name="text").required is False


def test_mcp_prompt_with_arguments():
    p = MCPPrompt(
        name="summarize",
        description="summarise something",
        arguments=[MCPPromptArgument(name="text", description=None, required=True)],
    )
    assert p.arguments[0].name == "text"
    assert p.arguments[0].required is True


def test_mcp_invocation_never_carries_args_or_result_content():
    """Security invariant (the dataclass docstring): an invocation record must
    NOT have any field that could hold call arguments or result content. This
    guards against a future field like `arguments`/`result` silently leaking
    user data into the persisted invocation log."""
    field_names = {f.name for f in dataclasses.fields(MCPInvocation)}
    forbidden = {"arguments", "args", "result", "content", "params", "payload", "output"}
    assert field_names.isdisjoint(forbidden), (
        f"MCPInvocation gained a content-bearing field: {field_names & forbidden}"
    )
    # And the optional fields default away when omitted.
    inv = MCPInvocation(
        id=None,
        timestamp=datetime(2026, 5, 20, tzinfo=UTC),
        resource_name="filesystem",
        capability_type="tool",
        capability_key="read_file",
        duration_ms=42,
        status="ok",
    )
    assert inv.error_message is None
    assert inv.session_id is None
