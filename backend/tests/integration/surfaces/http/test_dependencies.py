"""DI provider singletons — assert the "not configured" branches raise and
the setters wire the value back up.

The composition root calls each set_X() exactly once at startup; a get_X()
called before that must fail loudly rather than hand a route a None it will
later dereference with an opaque AttributeError. These tests pin that
contract: every get_X() raises a clear RuntimeError when its module global
was never set, and returns the set value afterwards.

get_actor() validation lives in test_pr14_fixes.py and is not duplicated here.
"""

import pytest

from coffer.surfaces.http import credential_composition as cred_comp
from coffer.surfaces.http import dependencies as deps

# Each tuple: (owning module, module global attr, getter, setter).
# The setter takes any value; the getter must raise when the global is None
# and return the set value afterwards.
_PROVIDERS = [
    (deps, "_resource_service", deps.get_resource_service, deps.set_resource_service),
    (deps, "_audit_service", deps.get_audit_service, deps.set_audit_service),
    (deps, "_retention_service", deps.get_retention_service, deps.set_retention_service),
    (deps, "_mcp_session_factory", deps.get_mcp_session_factory, deps.set_mcp_session_factory),
    (deps, "_capability_discovery", deps.get_capability_discovery, deps.set_capability_discovery),
    (deps, "_supervisor", deps.get_supervisor, deps.set_supervisor),
    (deps, "_preferences_repo", deps.get_preferences_repo, deps.set_preferences_repo),
    (deps, "_invocation_repo", deps.get_invocation_repo, deps.set_invocation_repo),
    (deps, "_health_repo", deps.get_health_repo, deps.set_health_repo),
    # credential_store + master_key_manager live in credential_composition;
    # dependencies re-exports them for import stability.
    (
        cred_comp,
        "_credential_store",
        cred_comp.get_credential_store,
        cred_comp.set_credential_store,
    ),
    (
        cred_comp,
        "_master_key_manager",
        cred_comp.get_master_key_manager,
        cred_comp.set_master_key_manager,
    ),
]


@pytest.fixture
def _reset_globals(monkeypatch):
    """Force every provider global to None and restore on teardown.

    monkeypatch.setattr restores the original module-level value automatically,
    so a test that sets a provider can't leak into the next test.
    """
    for mod, attr, _getter, _setter in _PROVIDERS:
        monkeypatch.setattr(mod, attr, None)
    yield


@pytest.mark.parametrize(
    ("mod", "attr", "getter", "setter"),
    _PROVIDERS,
    ids=[attr for _m, attr, _g, _s in _PROVIDERS],
)
def test_getter_raises_runtime_error_when_unset(mod, attr, getter, setter, _reset_globals):
    with pytest.raises(RuntimeError) as exc_info:
        getter()
    # The message must name the missing component, not be a bare RuntimeError.
    assert "not initialised" in str(exc_info.value), str(exc_info.value)


@pytest.mark.parametrize(
    ("mod", "attr", "getter", "setter"),
    _PROVIDERS,
    ids=[attr for _m, attr, _g, _s in _PROVIDERS],
)
def test_setter_then_getter_returns_value(mod, attr, getter, setter, _reset_globals):
    sentinel = object()
    setter(sentinel)
    assert getter() is sentinel
    # The setter must have written the named module global, not a copy.
    assert getattr(mod, attr) is sentinel
