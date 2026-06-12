"""Unit tests for the kind-agnostic BuiltinToolRegistry."""

import pytest

from coffer.application.builtin_tools import (
    COFFER_TOOL_PREFIX,
    BuiltinTool,
    BuiltinToolRegistry,
)


async def _noop_handler(_args: dict) -> dict:  # type: ignore[type-arg]
    return {}


def _tool(name: str) -> BuiltinTool:
    return BuiltinTool(
        name=name,
        description="",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_noop_handler,
    )


def test_empty_registry() -> None:
    r = BuiltinToolRegistry()
    assert len(r) == 0
    assert r.list() == []
    assert r.get("coffer__anything") is None
    assert not r.is_builtin("coffer__anything")


def test_register_and_lookup() -> None:
    r = BuiltinToolRegistry()
    r.register(_tool("search_knowledge"))
    assert len(r) == 1
    assert r.is_builtin(f"{COFFER_TOOL_PREFIX}search_knowledge")
    assert r.get(f"{COFFER_TOOL_PREFIX}search_knowledge") is not None
    assert r.get("search_knowledge") is None  # without prefix: no match


def test_register_rejects_prefixed_name() -> None:
    r = BuiltinToolRegistry()
    with pytest.raises(ValueError, match="coffer__"):
        r.register(_tool(f"{COFFER_TOOL_PREFIX}foo"))


def test_register_rejects_duplicates() -> None:
    r = BuiltinToolRegistry()
    r.register(_tool("foo"))
    with pytest.raises(ValueError, match="duplicate"):
        r.register(_tool("foo"))
