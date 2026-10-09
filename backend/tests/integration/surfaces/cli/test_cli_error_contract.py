"""Every command keeps the shared error and exit contract, on every path.

Spec resource-framework "Offer every management operation on the command
line": with ``--json`` a failure is one ``{"error", "exit_code"}`` object on
stderr; a change that waits for an approval exits 9; input the command cannot
read exits 6 with nothing sent. These are the paths a full CLI test run found
off-contract — a name that resolves to nothing, an old reader's refusal, a file
that is not UTF-8, a singular pending approval id, a test whose answer says it
failed — each checked against a daemon played by a recording transport.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _client, _io
from coffer.surfaces.cli.main import app

_runner = CliRunner()

Handler = Callable[[str, str, dict[str, Any]], httpx.Response]


def _ok(body: Any, status: int = 200) -> Handler:
    return lambda method, path, _kw: httpx.Response(
        status, json=body, request=httpx.Request(method, f"http://d/api/v1{path}")
    )


def _error(status: int, code: str, message: str, **details: Any) -> Handler:
    envelope = {"error": {"code": code, "message": message, "details": details}}
    return _ok(envelope, status)


class _Daemon:
    """Answers each request with ``handler`` and remembers what was sent."""

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def __enter__(self) -> _Daemon:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        self.calls.append((method, path, kw))
        return self.handler(method, path, kw)

    def get(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("POST", path, **kw)


@pytest.fixture
def daemon(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], _Daemon]:
    def install(handler: Handler) -> _Daemon:
        d = _Daemon(handler)
        monkeypatch.setattr(_client, "client_or_exit", lambda **_kw: (d, object()))
        return d

    return install


def _envelope(stderr: str) -> dict[str, Any]:
    """The one JSON object stderr must be, or the test fails on the text."""
    value = json.loads(stderr)
    assert set(value) >= {"error", "exit_code"}, value
    assert set(value["error"]) == {"code", "message", "details"}, value
    return dict(value)


# --- CLI-003: a file or stdin that is not UTF-8 -----------------------------------


@pytest.mark.parametrize("via", ["file", "stdin"])
def test_input_that_is_not_utf8_exits_6_with_nothing_sent(
    daemon: Callable[[Handler], _Daemon], tmp_path: Path, via: str
) -> None:
    d = daemon(_ok({"uid": "u"}))
    raw = b"\xff\xfe{\x00}\x00"
    path = tmp_path / "qa-cli-invalid-utf8.json"
    path.write_bytes(raw)
    data, stdin = (f"@{path}", None) if via == "file" else ("-", raw)
    result = _runner.invoke(
        app,
        [
            "custom-tool",
            "group",
            "create",
            "qa-cli-g",
            "--base-url",
            "http://127.0.0.1:1",
            "--data",
            data,
            "--json",
        ],
        input=stdin,
    )
    assert result.exit_code == 6, result.output
    env = _envelope(result.stderr)
    assert env["error"]["code"] == "CLI_INVALID_INPUT"
    assert env["exit_code"] == 6
    assert "UTF-8" in env["error"]["message"]
    assert result.stdout == ""
    assert d.calls == []


def test_a_utf8_file_with_chinese_text_still_reads(
    daemon: Callable[[Handler], _Daemon], tmp_path: Path
) -> None:
    d = daemon(_ok({"uid": "u", "name": "qa-cli-g"}))
    path = tmp_path / "body.json"
    path.write_text('{"description": "中文 描述"}', encoding="utf-8")
    result = _runner.invoke(
        app,
        [
            "custom-tool",
            "group",
            "create",
            "qa-cli-g",
            "--base-url",
            "http://127.0.0.1:1",
            "--data",
            f"@{path}",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert d.calls[-1][2]["json"]["description"] == "中文 描述"


# --- CLI-004: --json on name resolution and the older readers ---------------------


@pytest.mark.acceptance(
    spec="resource-framework", scenario="every failure path keeps the JSON error contract"
)
def test_a_name_that_resolves_to_nothing_is_a_json_error(
    daemon: Callable[[Handler], _Daemon],
) -> None:
    def handler(method: str, path: str, kw: dict[str, Any]) -> httpx.Response:
        if path == "/resources":
            return _ok({"resources": []})(method, path, kw)
        return _error(404, "RESOURCE_NOT_FOUND", "no such resource")(method, path, kw)

    daemon(handler)
    result = _runner.invoke(app, ["mcp", "show", "qa-cli-no-such-resource", "--json"])
    assert result.exit_code == 4, result.output
    env = _envelope(result.stderr)
    assert env["exit_code"] == 4
    assert env["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert env["error"]["details"] == {"kind": "mcp_server", "name": "qa-cli-no-such-resource"}
    assert result.stdout == ""


def test_a_name_that_resolves_to_nothing_reads_as_text_without_json(
    daemon: Callable[[Handler], _Daemon],
) -> None:
    daemon(_ok({"resources": []}))
    result = _runner.invoke(app, ["mcp", "show", "qa-cli-no-such-resource"])
    assert result.exit_code == 4
    assert "no mcp_server named 'qa-cli-no-such-resource'" in result.stderr


@pytest.mark.parametrize(
    "argv",
    [
        ["log", "audit", "--cursor", "qa-cli-invalid-cursor"],
        ["log", "mcp", "--cursor", "qa-cli-invalid-cursor"],
        ["log", "daemon"],
        ["secret", "list"],
        ["cli", "list"],
        ["vault", "problems"],
    ],
    ids=lambda a: " ".join(a[:2]),
)
def test_older_readers_render_a_refusal_as_json(
    daemon: Callable[[Handler], _Daemon], argv: list[str]
) -> None:
    daemon(_error(422, "CURSOR_INVALID", "qa-cli cursor is not one this list gave"))
    result = _runner.invoke(app, [*argv, "--json"])
    assert result.exit_code == 6, (argv, result.output)
    env = _envelope(result.stderr)
    assert env == {
        "error": {
            "code": "CURSOR_INVALID",
            "message": "qa-cli cursor is not one this list gave",
            "details": {},
        },
        "exit_code": 6,
    }
    assert result.stdout == ""


def test_a_daemon_that_cannot_start_is_a_json_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_client, "live_daemon", lambda: None)
    monkeypatch.setattr(_client, "_spawn_daemon", lambda: None)
    monkeypatch.setattr(_client, "_wait_for_daemon", lambda timeout: None)
    result = _runner.invoke(app, ["resource", "show", "qa-cli-absent", "--json"])
    assert result.exit_code == 3, result.output
    env = _envelope(result.stderr)
    assert env["error"]["code"] == "DAEMON_UNREACHABLE"
    assert env["exit_code"] == 3


# --- CLI-005: a pending answer named by a single id exits 9 -----------------------


@pytest.mark.acceptance(spec="resource-framework", scenario="a single pending approval exits 9")
@pytest.mark.parametrize(
    ("argv", "answer"),
    [
        (
            ["secret", "local-access", "request", "--set", "name=qa-cli-s"],
            {"local_access": "pending", "approval_id": "appr-1"},
        ),
        (
            ["settings", "approvals", "set", "--set", "require_approval=false"],
            {"require_approval": True, "pending_approval_id": "appr-1", "default_on": True},
        ),
    ],
    ids=["local-access", "approvals-off"],
)
@pytest.mark.parametrize("as_json", [True, False], ids=["json", "text"])
def test_a_single_pending_approval_exits_9_with_the_next_step(
    daemon: Callable[[Handler], _Daemon], argv: list[str], answer: dict[str, Any], as_json: bool
) -> None:
    daemon(_ok(answer, 202 if "pending_approval_id" in answer else 200))
    result = _runner.invoke(app, [*argv, *(["--json"] if as_json else [])])
    assert result.exit_code == 9, result.output
    if as_json:
        assert json.loads(result.stdout) == answer
        assert json.loads(result.stderr) == {
            "status": "pending_approval",
            "approval_ids": ["appr-1"],
            "next": "coffer approval approve appr-1",
        }
    else:
        assert "next: coffer approval approve appr-1" in result.stderr


def test_a_grant_already_on_is_not_pending(daemon: Callable[[Handler], _Daemon]) -> None:
    daemon(_ok({"local_access": "on", "approval_id": None}))
    result = _runner.invoke(
        app, ["secret", "local-access", "request", "--set", "name=qa-cli-s", "--json"]
    )
    assert result.exit_code == 0, result.output


def test_an_approval_id_beside_a_settled_state_is_not_pending() -> None:
    assert _io.pending_approvals({"status": "approved", "approval_id": "appr-1"}) == []
    assert _io.pending_approvals({"local_access": "pending", "approval_id": "appr-1"}) == ["appr-1"]


# --- CLI-008: a switched-off feature ------------------------------------------------


@pytest.mark.parametrize("as_json", [True, False], ids=["json", "text"])
@pytest.mark.parametrize(
    "argv", [["knowledge", "list"], ["log", "audit"]], ids=["route-command", "older-reader"]
)
def test_a_switched_off_feature_exits_1_and_names_no_removed_command(
    daemon: Callable[[Handler], _Daemon], argv: list[str], as_json: bool
) -> None:
    message = "knowledge is switched off on this machine — switch it on in Settings › Features"  # noqa: RUF001
    daemon(_error(404, "FEATURE_DISABLED", message, feature="knowledge"))
    result = _runner.invoke(app, [*argv, *(["--json"] if as_json else [])])
    assert result.exit_code == 1, result.output
    assert "config set" not in result.stderr
    if as_json:
        env = _envelope(result.stderr)
        assert env["error"]["code"] == "FEATURE_DISABLED"
        assert env["error"]["details"] == {"feature": "knowledge"}
        assert env["exit_code"] == 1
    else:
        assert "Settings › Features" in result.stderr  # noqa: RUF001


# --- CLI-012: --verbose reaches the generated commands ------------------------------


def test_verbose_adds_the_request_behind_an_error(daemon: Callable[[Handler], _Daemon]) -> None:
    daemon(_error(404, "RESOURCE_NOT_FOUND", "gone"))
    plain = _runner.invoke(app, ["resource", "show", "u" * 32, "--json"])
    loud = _runner.invoke(app, ["--verbose", "resource", "show", "u" * 32, "--json"])
    assert plain.exit_code == loud.exit_code == 4
    assert "request" not in _envelope(plain.stderr)
    request = _envelope(loud.stderr)["request"]
    assert request == {"method": "GET", "path": f"/api/v1/resources/{'u' * 32}", "status": 404}
    text = _runner.invoke(app, ["-v", "resource", "show", "u" * 32])
    assert f"GET /api/v1/resources/{'u' * 32} -> 404" in text.stderr


def test_verbose_never_prints_the_token(daemon: Callable[[Handler], _Daemon]) -> None:
    daemon(_error(500, "INTERNAL", "boom"))
    result = _runner.invoke(app, ["-v", "resource", "show", "u" * 32, "--json"])
    assert "X-Coffer-Token" not in result.stderr
    assert "test-token" not in result.stderr


# --- CLI-014: a test whose answer says it failed exits 7 ----------------------------


@pytest.mark.parametrize(
    "argv",
    [
        [
            "model",
            "test",
            "--data",
            '{"provider":"qa-cli-invalid","base_url":"http://127.0.0.1:1","model":"qa-cli-model"}',
        ],
        ["mcp", "test-config", "--data", '{"transport": {"type": "stdio", "command": "x"}}'],
    ],
    ids=["model-test", "mcp-test-config"],
)
def test_a_failed_test_result_exits_7_with_the_whole_answer(
    daemon: Callable[[Handler], _Daemon], argv: list[str]
) -> None:
    answer = {"ok": False, "error": "connection refused"}
    daemon(_ok(answer))
    result = _runner.invoke(app, [*argv, "--json"])
    assert result.exit_code == 7, result.output
    assert json.loads(result.stdout) == answer
    daemon(_ok({"ok": True}))
    passed = _runner.invoke(app, [*argv, "--json"])
    assert passed.exit_code == 0, passed.output


# --- CLI-002: coffer run with an --env-file it cannot read --------------------------


@pytest.mark.parametrize("problem", ["missing", "directory", "unreadable", "not-utf8"])
def test_an_env_file_that_cannot_be_read_exits_6_and_starts_nothing(
    daemon: Callable[[Handler], _Daemon], tmp_path: Path, problem: str
) -> None:
    d = daemon(_ok({"values": {}}))
    env_file = tmp_path / "qa-cli.env"
    if problem == "directory":
        env_file.mkdir()
    elif problem == "unreadable":
        env_file.write_text("A=1\n")
        env_file.chmod(0)
    elif problem == "not-utf8":
        env_file.write_bytes(b"A=\xff\xfe\n")
    marker = tmp_path / "child-ran"
    result = _runner.invoke(
        app,
        ["run", "--env-file", str(env_file), "--", "/bin/sh", "-c", f"touch {marker}"],
    )
    if problem == "unreadable":
        env_file.chmod(0o600)
    assert result.exit_code == 6, result.output
    assert "Traceback" not in result.output
    assert "--env-file" in result.stderr
    assert not marker.exists()
    assert d.calls == []


# --- CLI-009: secret set and mcp test speak --json -------------------------------------


def test_secret_set_json_prints_the_ref_and_never_the_value(
    daemon: Callable[[Handler], _Daemon],
) -> None:
    canary = "qa-cli-canary-value-0001"
    minted = {"ref": "s" * 26, "uri": f"coffer://secret/{'s' * 26}"}
    d = daemon(_ok(minted))
    result = _runner.invoke(
        app, ["secret", "set", "--name", "qa-cli-example", "--json"], input=canary
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"status": "stored", **minted}
    assert canary not in result.stdout + result.stderr
    assert d.calls[-1][2]["json"]["value"] == canary
    refused = _runner.invoke(app, ["secret", "set", "--json"], input=canary)
    assert refused.exit_code == 6
    assert _envelope(refused.stderr)["error"]["code"] == "CLI_INVALID_INPUT"


@pytest.mark.parametrize("ok", [True, False])
def test_mcp_test_json_prints_the_answer_and_keeps_exit_7(
    daemon: Callable[[Handler], _Daemon], ok: bool
) -> None:
    answer = {"ok": ok, "latency_ms": 3, "error_message": None if ok else "spawn failed"}

    def handler(method: str, path: str, kw: dict[str, Any]) -> httpx.Response:
        if path == "/resources":
            return _ok({"resources": [{"uid": "m" * 32, "name": "qa-cli-m"}]})(method, path, kw)
        if path.endswith("/refresh"):
            return _ok({"tools": [{}], "prompts": [], "resources": []})(method, path, kw)
        return _ok(answer)(method, path, kw)

    daemon(handler)
    result = _runner.invoke(app, ["mcp", "test", "qa-cli-m", "--json"])
    assert result.exit_code == (0 if ok else 7), result.output
    out = json.loads(result.stdout)
    assert out["ok"] is ok
    assert out["capabilities"] == {"tools": 1, "prompts": 0, "resources": 0, "from_cache": False}


# --- CLI-006: management groups are visible -----------------------------------------


@pytest.mark.acceptance(
    spec="resource-framework", scenario="management commands are visible in help"
)
def test_memory_and_proxy_management_commands_show_in_root_help() -> None:
    root = _runner.invoke(app, ["--help"])
    assert root.exit_code == 0
    assert "memory" in root.stdout and "proxy" in root.stdout
    memory = _runner.invoke(app, ["memory", "--help"])
    assert "sync" in memory.stdout and "hook" not in memory.stdout.split("Commands")[-1]
    proxy = _runner.invoke(app, ["proxy", "--help"])
    assert "status" in proxy.stdout and " token " not in proxy.stdout
