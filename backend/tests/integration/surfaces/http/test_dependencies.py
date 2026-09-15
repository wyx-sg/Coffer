"""DI provider singletons — assert the "not configured" branches raise and
the setters wire the value back up.

The composition root calls each set_X() exactly once at startup; a get_X()
called before that must fail loudly rather than hand a route a None it will
later dereference with an opaque AttributeError. These tests pin that
contract: every get_X() raises a clear RuntimeError when its module global
was never set, and returns the set value afterwards.

The hub (``dependencies``) is kind-agnostic; every kind publishes its own
pairs from its own module. All of them are enumerated here, and a guard test
fails the moment a module grows a ``set_*`` this table does not list.

get_actor() validation lives in test_pr14_fixes.py and is not duplicated here.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

from coffer.surfaces.http import agent_dependencies as agent_deps
from coffer.surfaces.http import credential_composition as cred_comp
from coffer.surfaces.http import dependencies as deps
from coffer.surfaces.http import provider_dependencies as provider_deps
from coffer.surfaces.http import skill_dependencies as skill_deps
from coffer.surfaces.http import workspace_dependencies as workspace_deps
from coffer.surfaces.http.chat import dependencies as chat_deps
from coffer.surfaces.http.knowledge import dependencies as knowledge_deps
from coffer.surfaces.http.mcp import dependencies as mcp_deps
from coffer.surfaces.http.memory import dependencies as memory_deps

_Provider = tuple[ModuleType, str, Callable[[], Any], Callable[[Any], None]]


def _pairs(mod: ModuleType, *attrs: str) -> list[_Provider]:
    """One ``(module, "_attr", get_attr, set_attr)`` tuple per global name."""
    return [(mod, attr, getattr(mod, f"get{attr}"), getattr(mod, f"set{attr}")) for attr in attrs]


# Each tuple: (owning module, module global attr, getter, setter).
# The setter takes any value; the getter must raise when the global is None
# and return the set value afterwards.
_PROVIDERS: list[_Provider] = [
    # kind-agnostic hub
    *_pairs(
        deps,
        "_resource_service",
        "_audit_service",
        "_retention_service",
        "_internal_engine_config_service",
    ),
    # mcp kind
    *_pairs(
        mcp_deps,
        "_mcp_session_factory",
        "_capability_discovery",
        "_supervisor",
        "_preferences_repo",
        "_invocation_repo",
        "_health_repo",
    ),
    # agent kind (+ its workspace facets)
    *_pairs(
        agent_deps,
        "_agent_service",
        "_auto_detect_service",
        "_agent_config_file_service",
        "_agent_mcp_service",
        "_agent_model_catalogue",
    ),
    *_pairs(
        workspace_deps,
        "_agent_mcp_entry_service",
        "_agent_plugin_service",
        "_agent_native_memory_service",
        "_agent_transcript_service",
    ),
    # skill kind
    *_pairs(skill_deps, "_skill_service"),
    # knowledge kind
    *_pairs(knowledge_deps, "_knowledge_service", "_search_service", "_ingest_service"),
    # memory kind
    *_pairs(
        memory_deps,
        "_memory_service",
        "_memory_override_repo",
        "_memory_delivery_service",
    ),
    # turn platform (chat)
    *_pairs(
        chat_deps,
        "_chat_service",
        "_turn_orchestrator",
        "_agent_registry",
        "_model_catalog",
    ),
    # provider kind
    *_pairs(provider_deps, "_provider_service", "_introspection_service"),
    # credential store + master key
    *_pairs(cred_comp, "_credential_store", "_master_key_manager"),
]

_MODULES: list[ModuleType] = sorted(
    {mod for mod, _a, _g, _s in _PROVIDERS}, key=lambda m: m.__name__
)


def _id(mod: ModuleType, attr: str) -> str:
    """``mcp.dependencies._health_repo`` — the module short-name disambiguates
    the four kinds whose module is itself called ``dependencies``."""
    return f"{mod.__name__.removeprefix('coffer.surfaces.http.')}{attr}"


_IDS = [_id(mod, attr) for mod, attr, _g, _s in _PROVIDERS]


@pytest.fixture
def _reset_globals(monkeypatch):
    """Force every provider global to None and restore on teardown.

    monkeypatch.setattr restores the original module-level value automatically,
    so a test that sets a provider can't leak into the next test.
    """
    for mod, attr, _getter, _setter in _PROVIDERS:
        monkeypatch.setattr(mod, attr, None)
    yield


@pytest.mark.parametrize(("mod", "attr", "getter", "setter"), _PROVIDERS, ids=_IDS)
def test_getter_raises_runtime_error_when_unset(mod, attr, getter, setter, _reset_globals):
    with pytest.raises(RuntimeError) as exc_info:
        getter()
    # The message must name the missing component, not be a bare RuntimeError.
    assert "not initialised" in str(exc_info.value), str(exc_info.value)


@pytest.mark.parametrize(("mod", "attr", "getter", "setter"), _PROVIDERS, ids=_IDS)
def test_setter_then_getter_returns_value(mod, attr, getter, setter, _reset_globals):
    sentinel = object()
    setter(sentinel)
    assert getter() is sentinel
    # The setter must have written the named module global, not a copy.
    assert getattr(mod, attr) is sentinel


@pytest.mark.parametrize("mod", _MODULES, ids=[m.__name__ for m in _MODULES])
def test_every_setter_in_the_module_is_enumerated(mod):
    """A ``set_*`` added to any DI module must be added to ``_PROVIDERS`` too,
    or the two contracts above silently stop covering it."""
    declared = {
        name.removeprefix("set")
        for name, obj in inspect.getmembers(mod, inspect.isfunction)
        if name.startswith("set_") and obj.__module__ == mod.__name__
    }
    enumerated = {attr for m, attr, _g, _s in _PROVIDERS if m is mod}
    assert declared == enumerated, (
        f"{mod.__name__}: setters {sorted(declared - enumerated)} are not enumerated; "
        f"enumerated {sorted(enumerated - declared)} have no setter"
    )
