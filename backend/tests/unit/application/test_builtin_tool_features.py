"""Builtin tools owned by an experimental feature leave the registry while it is off.

Spec experimental-features "Close every surface of a switched-off feature": the
registry asks the switch on every read, so the gateway's list and its call path
(both read the registry) see the same answer, and a switch needs no restart.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.domain.features import FeatureUnknown


async def _handler(_args: dict[str, Any]) -> dict[str, Any]:
    return {}


def _tool(name: str, feature: str | None = None) -> BuiltinTool:
    return BuiltinTool(
        name=name, description="x", input_schema={}, handler=_handler, feature=feature
    )


def _registry(state: dict[str, bool]) -> BuiltinToolRegistry:
    reg = BuiltinToolRegistry(feature_enabled=lambda key: state[key])
    reg.register(_tool("recall", "memory"))
    reg.register(_tool("write", "knowledge"))
    reg.register(_tool("diagnose"))
    return reg


def test_a_tool_whose_feature_is_off_is_neither_listed_nor_found() -> None:
    state = {"memory": False, "knowledge": True}
    reg = _registry(state)
    assert [t.name for t in reg.list()] == ["write", "diagnose"]
    assert reg.get("coffer__recall") is None
    assert not reg.is_builtin("coffer__recall")
    assert len(reg) == 2

    state["memory"] = True
    assert reg.is_builtin("coffer__recall")
    assert [t.name for t in reg.list()] == ["recall", "write", "diagnose"]


def test_without_a_switch_every_tool_is_there() -> None:
    reg = BuiltinToolRegistry()
    reg.register(_tool("recall", "memory"))
    assert reg.is_builtin("coffer__recall")


def test_a_tool_naming_an_unregistered_feature_is_refused_at_registration() -> None:
    with pytest.raises(FeatureUnknown):
        BuiltinToolRegistry().register(_tool("x", "workflow"))


def test_registering_a_hidden_tool_twice_is_still_a_duplicate() -> None:
    reg = _registry({"memory": False, "knowledge": False})
    with pytest.raises(ValueError, match="duplicate"):
        reg.register(_tool("recall", "memory"))
