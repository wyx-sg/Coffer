"""The command line offers every management operation the web UI and desktop do.

Spec resource-framework "Offer every management operation on the command
line". The registry is compared with the routes the web UI calls and the
desktop shell's commands; every declared command is run against a recording
transport to prove it calls the route it claims; and every leaf of the live
tree is either a recorded UI operation or a command with a non-UI reason.
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import typer
from typer.testing import CliRunner

from coffer.surfaces.cli import _client
from coffer.surfaces.cli._route_command import MOUNTED, RouteCommand
from coffer.surfaces.cli.command_reasons import COMMAND_REASONS, Reason
from coffer.surfaces.cli.main import app
from coffer.surfaces.cli.registry import EXEMPT, OPERATIONS

_REPO = Path(__file__).resolve().parents[5]
_runner = CliRunner()


def _coverage() -> Any:
    spec = importlib.util.spec_from_file_location(
        "cli_coverage", _REPO / "scripts" / "cli_coverage.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _walk(cmd: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    yield path, cmd
    for name, sub in (getattr(cmd, "commands", None) or {}).items():
        yield from _walk(sub, (*path, name))


def _leaves() -> dict[str, Any]:
    root = typer.main.get_command(app)
    return {" ".join(p): c for p, c in _walk(root) if p and not getattr(c, "commands", None)}


@pytest.mark.acceptance(
    spec="resource-framework", scenario="the command line covers every web UI and desktop operation"
)
def test_every_ui_route_and_desktop_command_has_a_command() -> None:
    coverage = _coverage()
    assert coverage.problems() == []
    # The audit sees the UI's calls: a route the UI calls is either covered or exempt.
    ui = coverage.frontend_routes()
    assert len(ui) > 200
    covered = {(o.method, o.route) for o in OPERATIONS}
    # The event stream is plumbing the page subscribes to, not an operation.
    assert ui <= covered | set(EXEMPT) | set(coverage.STREAM_EXEMPT)
    assert {cat for cat, _ in EXEMPT.values()} <= {"file-content", "window", "internal"}


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a route the web UI calls without a command fails the test"
)
def test_a_route_without_a_command_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    coverage = _coverage()
    real = coverage.frontend_routes
    monkeypatch.setattr(coverage, "frontend_routes", lambda: real() | {("POST", "/brand/new")})
    assert any("/brand/new" in p for p in coverage.problems())


@pytest.mark.acceptance(
    spec="resource-framework", scenario="every command is a UI operation or has a recorded reason"
)
def test_every_command_is_recorded_or_has_a_reason() -> None:
    leaves = set(_leaves())
    recorded = {o.command for o in OPERATIONS}
    assert leaves == recorded | set(COMMAND_REASONS), leaves ^ (recorded | set(COMMAND_REASONS))
    assert recorded.isdisjoint(COMMAND_REASONS)
    for path, (reason, why) in COMMAND_REASONS.items():
        assert isinstance(reason, Reason) and why.strip(), path
    hidden = {p for p, c in _leaves().items() if c.hidden}
    assert hidden == {"memory hook", "proxy token"}


def test_every_group_renders_its_help() -> None:
    root = typer.main.get_command(app)
    for path, cmd in _walk(root):
        if path and getattr(cmd, "commands", None):
            result = _runner.invoke(app, [*path, "--help"])
            assert result.exit_code == 0, (path, result.output)


class _Recorder:
    """A daemon that answers every request with an empty success, and remembers them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any], Any]] = []

    def __enter__(self) -> _Recorder:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        self.calls.append((method, path, kw.get("params") or {}, kw.get("json")))
        if method == "GET" and path == "/resources":
            body: Any = {"resources": [{"uid": "u" * 32, "name": "x"}]}
        else:
            body = {"ok": True, "items": [], "resources": []}
        return httpx.Response(200, json=body, request=httpx.Request(method, f"http://d{path}"))

    get = lambda self, path, **kw: self.request("GET", path, **kw)  # noqa: E731


def _pattern(route: str) -> re.Pattern[str]:
    return re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(route)) + "$")


@pytest.mark.acceptance(
    spec="resource-framework", scenario="each declared command calls the route it records"
)
@pytest.mark.parametrize("spec", MOUNTED, ids=lambda s: s.command)
def test_each_declared_command_calls_its_route(
    spec: RouteCommand, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(_client, "client_or_exit", lambda **_kw: (recorder, object()))
    args = [*spec.command.split(" ")]
    args += ["x" for _ in re.findall(r"\{[^}]+\}", spec.route)]
    if spec.body:
        args += ["--data", '{"probe": 1}', "--set", "nested.flag=true"]
    result = _runner.invoke(app, [*args, "--json"])
    assert result.exit_code == 0, result.output
    sent = [
        c
        for c in recorder.calls
        if not (c[0] == "GET" and c[1] == "/resources" and spec.method != "GET")
    ]
    target = [c for c in sent if c[0] == spec.method and _pattern(spec.route).match(c[1])]
    assert target, (spec.command, recorder.calls)
    _method, _path, params, body = target[-1]
    for key, value in spec.fixed_query.items():
        assert params.get(key) == value
    if spec.body:
        assert body["probe"] == 1 and body["nested"] == {"flag": True}
        for key, value in spec.fixed_body.items():
            assert body[key] == value
    json.loads(result.stdout)


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="a command takes JSON from a file or stdin and fails with a stable code",
)
def test_input_from_stdin_and_errors_as_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(_client, "client_or_exit", lambda **_kw: (recorder, object()))
    result = _runner.invoke(
        app,
        ["knowledge", "create", "--data", "-", "--json"],
        input='{"name": "ops", "description": "d"}',
    )
    assert result.exit_code == 0, result.output
    assert recorder.calls[-1][3] == {"name": "ops", "description": "d"}
    body = tmp_path / "body.json"
    body.write_text('{"name": "docs", "description": "e"}')
    _runner.invoke(app, ["knowledge", "create", "--data", f"@{body}"])
    assert recorder.calls[-1][3]["name"] == "docs"
    bad = _runner.invoke(app, ["knowledge", "create", "--data", "{nope", "--json"])
    assert bad.exit_code == 6
    assert json.loads(bad.stderr)["error"]["code"] == "CLI_INVALID_INPUT"

    class _Refusing(_Recorder):
        def request(self, method: str, path: str, **kw: Any) -> httpx.Response:
            envelope = {"error": {"code": "RESOURCE_NOT_FOUND", "message": "gone", "details": {}}}
            return httpx.Response(
                404, json=envelope, request=httpx.Request(method, f"http://d{path}")
            )

    monkeypatch.setattr(_client, "client_or_exit", lambda **_kw: (_Refusing(), object()))
    missing = _runner.invoke(app, ["resource", "show", "nope", "--json"])
    assert missing.exit_code == 4
    assert json.loads(missing.stderr) == {
        "error": {"code": "RESOURCE_NOT_FOUND", "message": "gone", "details": {}},
        "exit_code": 4,
    }
