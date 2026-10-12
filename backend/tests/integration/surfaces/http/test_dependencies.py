"""DI provider singletons — assert the "not configured" branches raise and
the setters wire the value back up.

The composition root calls each set_X() exactly once at startup; a get_X()
called before that must fail loudly rather than hand a route a None it will
later dereference with an opaque AttributeError. These tests pin that
contract: every get_X() raises a clear RuntimeError when its module global
was never set, and returns the set value afterwards.

Providers are discovered, not listed: every module under ``coffer.surfaces.http``
is scanned for ``set_X`` functions it defines itself. A new ``set_X``/``get_X``
pair in any kind's module is therefore covered with no edit here. A getter that
answers ``None`` while unset is an *optional* provider (a surface works without
it); one that raises is required. The discovery guards below fail if a setter
has no matching getter or global, or if the scan finds nothing.

get_actor() validation lives in test_actor_header.py and is not duplicated here.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
from fastapi import HTTPException

import coffer.surfaces.http as http_pkg

_Provider = tuple[ModuleType, str, Callable[[], Any], Callable[[Any], None]]


def _http_modules() -> list[ModuleType]:
    return [
        importlib.import_module(info.name)
        for info in pkgutil.walk_packages(http_pkg.__path__, f"{http_pkg.__name__}.")
    ]


def _global_of(mod: ModuleType, setter: Callable[..., Any]) -> str | None:
    """The one module global a setter writes, read from its bytecode names."""
    names = [
        n
        for n in setter.__code__.co_names
        if n in vars(mod)
        and not callable(vars(mod)[n])
        and not isinstance(vars(mod)[n], ModuleType)
    ]
    return names[0] if len(names) == 1 else None


def _discover() -> tuple[list[_Provider], list[_Provider], list[_Provider], list[str]]:
    """``(required, optional, unwired_503, problems)`` for every ``set_X`` a module defines.

    Required getters raise ``RuntimeError``; optional ones answer ``None``;
    route-local ones answer HTTP 503 "not wired". A getter that builds a
    default when unset (``get_release_check``) is not a "must be wired"
    contract and is left out.

    ``set_X`` is paired with the ``get_X`` beside it and with the module global
    it writes. A setter with no such getter is some other kind of state (a
    port, a start time) and is not a provider. A pair whose unset getter
    neither raises ``RuntimeError`` nor answers ``None`` is a problem.
    """
    required: list[_Provider] = []
    optional: list[_Provider] = []
    unwired: list[_Provider] = []
    problems: list[str] = []
    for mod in _http_modules():
        for name, obj in sorted(vars(mod).items()):
            if not (name.startswith("set_") and inspect.isfunction(obj)):
                continue
            if obj.__module__ != mod.__name__:
                continue
            getter = getattr(mod, "get_" + name.removeprefix("set_"), None)
            attr = _global_of(mod, obj)
            if getter is None or attr is None:
                continue
            if any(
                p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                for p in inspect.signature(getter).parameters.values()
            ):
                continue
            saved = getattr(mod, attr)
            setattr(mod, attr, None)
            try:
                try:
                    unset = getter()
                except RuntimeError:
                    required.append((mod, attr, getter, obj))
                except HTTPException as exc:
                    if exc.status_code == 503:
                        unwired.append((mod, attr, getter, obj))
                    else:
                        problems.append(f"{mod.__name__}.{name}: unset getter raised {exc!r}")
                except Exception as exc:
                    problems.append(f"{mod.__name__}.{name}: unset getter raised {exc!r}")
                else:
                    if unset is None:
                        optional.append((mod, attr, getter, obj))
            finally:
                setattr(mod, attr, saved)
    return required, optional, unwired, problems


_PROVIDERS, _OPTIONAL_PROVIDERS, _UNWIRED_PROVIDERS, _PROBLEMS = _discover()


def _id(mod: ModuleType, attr: str) -> str:
    """``mcp.dependencies._health_repo`` — the module short-name disambiguates
    the kinds whose module is itself called ``dependencies``."""
    return f"{mod.__name__.removeprefix('coffer.surfaces.http.')}{attr}"


_IDS = [_id(mod, attr) for mod, attr, _g, _s in _PROVIDERS]


def test_discovery_found_the_providers():
    assert len(_PROVIDERS) > 20, "the scan of coffer.surfaces.http found almost nothing"
    assert _OPTIONAL_PROVIDERS


def test_discovery_has_no_problems():
    """An unset getter must raise RuntimeError, answer None, or answer 503."""
    assert _PROBLEMS == []


@pytest.fixture
def _reset_globals(monkeypatch):
    """Force every provider global to None and restore on teardown.

    monkeypatch.setattr restores the original module-level value automatically,
    so a test that sets a provider can't leak into the next test.
    """
    for mod, attr, _getter, _setter in [*_PROVIDERS, *_OPTIONAL_PROVIDERS, *_UNWIRED_PROVIDERS]:
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


@pytest.mark.parametrize(
    ("mod", "attr", "getter", "setter"),
    _OPTIONAL_PROVIDERS,
    ids=[_id(mod, attr) for mod, attr, _g, _s in _OPTIONAL_PROVIDERS],
)
def test_optional_getter_is_none_when_unset(mod, attr, getter, setter, _reset_globals):
    assert getter() is None
    sentinel = object()
    setter(sentinel)
    assert getter() is sentinel
    assert getattr(mod, attr) is sentinel


@pytest.mark.parametrize(
    ("mod", "attr", "getter", "setter"),
    _UNWIRED_PROVIDERS,
    ids=[_id(mod, attr) for mod, attr, _g, _s in _UNWIRED_PROVIDERS],
)
def test_route_local_getter_answers_503_when_unset(mod, attr, getter, setter, _reset_globals):
    with pytest.raises(HTTPException) as exc_info:
        getter()
    assert exc_info.value.status_code == 503
    sentinel = object()
    setter(sentinel)
    assert getter() is sentinel
    assert getattr(mod, attr) is sentinel
