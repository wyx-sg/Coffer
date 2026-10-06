"""The static CLI coverage gate sees dynamic routes, the event stream and hidden groups.

Synthetic inputs only: the gate's own run over the real tree is
``scripts/cli_coverage.py --check`` (a static route/visibility check, not an
end-to-end or option-semantics check).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import click
import pytest

_REPO = Path(__file__).resolve().parents[5]


def _coverage() -> Any:
    spec = importlib.util.spec_from_file_location(
        "cli_coverage", _REPO / "scripts" / "cli_coverage.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_literal_routes_are_still_found() -> None:
    text = 'getApiClient().GET("/agents/{uid}", { params })'
    assert _coverage().scan_routes(text) == {("GET", "/agents/{uid}")}


def test_template_literal_with_cast_union_expands_to_each_alternative() -> None:
    text = """
    getApiClient().POST(
      `/resources/mcp_server/{uid}/capabilities/{capability_type}/${op}` as
        | "/resources/mcp_server/{uid}/capabilities/{capability_type}/enable"
        | "/resources/mcp_server/{uid}/capabilities/{capability_type}/disable",
      { body },
    )
    """
    assert _coverage().scan_routes(text) == {
        ("POST", "/resources/mcp_server/{uid}/capabilities/{capability_type}/enable"),
        ("POST", "/resources/mcp_server/{uid}/capabilities/{capability_type}/disable"),
    }


def test_template_literal_with_ternary_expands() -> None:
    text = 'c.POST(`/x/{uid}/${on ? "enable" : "disable"}`, {})'
    assert _coverage().scan_routes(text) == {
        ("POST", "/x/{uid}/enable"),
        ("POST", "/x/{uid}/disable"),
    }


def test_unresolvable_template_segment_becomes_a_param_so_it_cannot_match() -> None:
    text = "c.GET(`/things/${id}/children`, {})"
    assert _coverage().scan_routes(text) == {("GET", "/things/{param}/children")}


def test_event_stream_fetch_is_seen() -> None:
    text = 'const r = await fetch(`${base}/events`, { method: "GET", headers, signal });'
    assert _coverage().scan_routes(text) == {("GET", "/events")}


def test_a_new_dynamic_route_is_reported_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    coverage = _coverage()
    real = coverage.frontend_routes
    monkeypatch.setattr(coverage, "frontend_routes", lambda: real() | {("POST", "/z/{param}/go")})
    assert any("/z/{param}/go" in p for p in coverage.problems())


def test_events_is_exempt_with_a_reason() -> None:
    coverage = _coverage()
    reason = coverage.STREAM_EXEMPT[("GET", "/events")]
    assert reason.strip()
    assert not any("/events" in p for p in coverage.problems())


def _tree() -> click.Group:
    root = click.Group("coffer")
    shown = click.Group("shown")
    shown.add_command(click.Command("leaf"))
    shown.add_command(click.Command("secret", hidden=True))
    hidden_group = click.Group("ghost", hidden=True)
    hidden_group.add_command(click.Command("leaf"))
    root.add_command(shown)
    root.add_command(hidden_group)
    return root


def test_visibility_flags_hidden_leaf_and_hidden_ancestor() -> None:
    probs, visible, allowed = _coverage().visibility(
        _tree(), ["shown leaf", "shown secret", "ghost leaf"], {}
    )
    assert visible == 1 and allowed == 0
    assert any("shown secret" in p for p in probs)
    assert any("ghost leaf" in p for p in probs)


def test_visibility_allowlist_passes_and_stale_entries_fail() -> None:
    allow = {"shown secret": "program only", "ghost leaf": "program only"}
    probs, visible, allowed = _coverage().visibility(
        _tree(), ["shown leaf", "shown secret", "ghost leaf"], allow
    )
    assert probs == [] and visible == 1 and allowed == 2
    probs, *_ = _coverage().visibility(_tree(), ["shown leaf"], {"shown leaf": "x"})
    assert any("shown leaf" in p and "not hidden" in p for p in probs)


def test_visibility_reports_a_command_missing_from_the_tree() -> None:
    probs, *_ = _coverage().visibility(_tree(), ["nope here"], {})
    assert any("nope here" in p for p in probs)
