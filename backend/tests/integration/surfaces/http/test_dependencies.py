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

from coffer.surfaces.http import dependencies as deps

# Each tuple: (module global attr, getter, setter). The setter takes any value;
# the getter must raise when the global is None and return the value otherwise.
_PROVIDERS = [
    ("_resource_service", deps.get_resource_service, deps.set_resource_service),
    ("_audit_service", deps.get_audit_service, deps.set_audit_service),
    ("_retention_service", deps.get_retention_service, deps.set_retention_service),
    ("_mcp_session_factory", deps.get_mcp_session_factory, deps.set_mcp_session_factory),
    ("_capability_discovery", deps.get_capability_discovery, deps.set_capability_discovery),
    ("_supervisor", deps.get_supervisor, deps.set_supervisor),
    ("_preferences_repo", deps.get_preferences_repo, deps.set_preferences_repo),
    ("_invocation_repo", deps.get_invocation_repo, deps.set_invocation_repo),
    ("_health_repo", deps.get_health_repo, deps.set_health_repo),
    ("_credential_store", deps.get_credential_store, deps.set_credential_store),
]


@pytest.fixture
def _reset_globals(monkeypatch):
    """Force every provider global to None and restore on teardown.

    monkeypatch.setattr restores the original module-level value automatically,
    so a test that sets a provider can't leak into the next test.
    """
    for attr, _getter, _setter in _PROVIDERS:
        monkeypatch.setattr(deps, attr, None)
    yield


@pytest.mark.parametrize(
    ("attr", "getter", "setter"),
    _PROVIDERS,
    ids=[attr for attr, _g, _s in _PROVIDERS],
)
def test_getter_raises_runtime_error_when_unset(attr, getter, setter, _reset_globals):
    with pytest.raises(RuntimeError) as exc_info:
        getter()
    # The message must name the missing component, not be a bare RuntimeError.
    assert "not initialised" in str(exc_info.value), str(exc_info.value)


@pytest.mark.parametrize(
    ("attr", "getter", "setter"),
    _PROVIDERS,
    ids=[attr for attr, _g, _s in _PROVIDERS],
)
def test_setter_then_getter_returns_value(attr, getter, setter, _reset_globals):
    sentinel = object()
    setter(sentinel)
    assert getter() is sentinel
    # The setter must have written the named module global, not a copy.
    assert getattr(deps, attr) is sentinel
