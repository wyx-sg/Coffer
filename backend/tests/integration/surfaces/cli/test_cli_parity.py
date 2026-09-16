"""Acceptance tests for US4 — CLI parity with the UI.

Scenario 1: every UI-visible operation has a CLI subcommand.
Scenario 2: the CLI surfaces errors in the same human-readable form as the UI.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app
from coffer.surfaces.http.auth import set_active_token

runner = CliRunner()


#: Every command group the CLI composition root registers, and every
#: subcommand each one registers, written down as an oracle. Asserted for
#: EXACT equality against the live command tree, in both directions: a UI
#: operation that ships without a CLI counterpart goes red here, and so does a
#: CLI command that appears without anyone deciding on it. Nested groups are
#: keyed by their full path ("mcp tool"), so a group's own subcommands are
#: covered too.
_EXPECTED_GROUPS: dict[str, set[str]] = {
    # "port" has no UI counterpart to be at parity with, and deliberately so:
    # the daemon binds 8000 and refuses to start when it cannot, so the state
    # the setting most needs changing from is one where no page the daemon
    # serves can be reached. It is listed here because it must not be dropped,
    # not because a card mirrors it. "restart" is how a change takes effect,
    # for the same reason a running daemon cannot move.
    "daemon": {"start", "stop", "restart", "status", "rotate-token", "port"},
    "daemon port": {"show", "set", "clear"},
    # `coffer open` is the one group with NO subcommands: it is a single action
    # (open the UI at the running daemon's origin), expressed as an
    # invoke_without_command callback. Its surface is its two options, which
    # _OPTION_ONLY_GROUPS asserts instead — so the empty set here is a
    # narrowed claim, not an unchecked hole.
    "open": set(),
    "resource": {"list", "show", "enable", "disable", "delete"},
    "scope": {"show", "set", "clear"},
    "audit": {"list"},
    "retention": {"list", "set", "prune-now"},
    "mcp": {
        "add",
        "remove",
        "list",
        "show",
        "refresh",
        "test",
        "tool",
        "resource",
        "prompt",
        "invocations",
    },
    "mcp tool": {"list", "enable", "disable"},
    "mcp resource": {"list", "enable", "disable"},
    "mcp prompt": {"list", "enable", "disable"},
    "credentials": {"set", "get", "list", "delete", "storage"},
    "agent": {
        "add",
        "edit",
        "rm",
        "list",
        "show",
        "detect",
        "config",
        "mcp",
        "plugin",
        "native-memory",
        "native-memory-files",
        "transcript",
        "transcripts",
    },
    "agent config": {"files", "ls", "cat", "write", "edit", "rm"},
    "agent mcp": {"status", "install", "uninstall", "adopt", "entries", "remove-entry"},
    "agent plugin": {"list", "enable", "disable", "uninstall"},
    "channel": {"register", "list", "status", "pair", "bind", "notify"},
    "skill": {"list", "show", "import", "adopt", "rm", "unmanaged", "rm-unmanaged", "verify"},
    "knowledge": {
        "collections",
        "create",
        "delete",
        "grep",
        "ls",
        "organize",
        "read",
        "search",
        "upload",
        "write",
    },
    "memory": {
        "context",
        "delivery",
        "delivery-install",
        "delivery-remove",
        "fact",
        "facts",
        "organize",
        "partitions",
        "sync",
    },
    "provider": {"add", "edit", "rm", "list", "show", "key", "switch", "internal-default"},
    "sync": {
        "adopt",
        "confirm",
        "history",
        "key",
        "machine",
        "now",
        "rebuild",
        "reject",
        "remote",
        "restore",
        "rollback",
        "status",
    },
    "sync key": {"export", "import", "fingerprint"},
    "sync machine": {"list", "rename", "remove"},
    "sync remote": {"show", "set", "clear"},
}

#: The groups whose surface is options rather than subcommands. Each is
#: claimed by the long options a caller can pass, since an empty subcommand
#: set would otherwise assert nothing about them.
_OPTION_ONLY_GROUPS: dict[str, set[str]] = {
    "open": {"--json", "--no-browser"},
}

#: The UI operations that have NO CLI counterpart today — the exemptions to
#: US4's claim, written down instead of left out.
#:
#: The table above is an oracle of what the CLI *registers*; it cannot see an
#: operation the UI has and the CLI simply never grew, so widening it by
#: itself would have made the scenario's claim ("every UI-visible operation
#: has a CLI subcommand") louder without making it truer. These three are what
#: extending it to all fifteen groups surfaced. Each is asserted below to be
#: STILL a gap, so closing one reds this test and forces its exemption to be
#: deleted — a fence that admits its holes and notices when one is filled.
#:
#: None of the three is fixed here: each is a CLI command that has to be
#: designed, not a test change.
_KNOWN_PARITY_GAPS: dict[str, str] = {
    "agent model": (
        "The model an agent answers with is bound only through the chat page, "
        "via PATCH /api/v1/chat/conversations/{id}/agent-config. No CLI path "
        "sets it: `coffer agent add|edit` take --config-dir and --description "
        "and nothing else, and there is no `coffer agent model`."
    ),
    "provider use-builtin": (
        "POST /api/v1/providers/use-builtin/{wire} exists and the Model "
        "providers page calls it — reverting a wire protocol to the agent's "
        "own built-in credentials. `coffer provider` has activate's half "
        "(`switch`) but not this one."
    ),
    "memory files": (
        "GET /api/v1/memory/partitions/{name}/files and .../files/content "
        "back the memory detail page's file tree and viewer. `coffer memory` "
        "reaches facts and partitions but cannot browse or read the files."
    ),
}


def _subcommands(path: str) -> set[str]:
    """The subcommand names registered under `path` in the live command tree.

    Read off the click tree rather than scraped out of ``--help``: the help is
    Rich-rendered into a width-dependent table, so a long name can wrap or be
    elided and a substring check would then pass or fail for reasons that have
    nothing to do with parity.
    """
    from typer.main import get_command

    node: object = get_command(app)
    for part in path.split():
        commands = getattr(node, "commands", {})
        assert part in commands, f"no command group '{part}' under '{path}'"
        node = commands[part]
    return set(getattr(node, "commands", {}))


def _long_options(path: str) -> set[str]:
    """Every long option flag declared on the command at `path`."""
    from typer.main import get_command

    node: object = get_command(app)
    for part in path.split():
        node = getattr(node, "commands", {})[part]
    return {
        opt
        for param in getattr(node, "params", [])
        for opt in getattr(param, "opts", [])
        if opt.startswith("--")
    }


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="command line covers every visual operation",
)
def test_cli_covers_every_visual_operation():
    """The CLI's command tree is exactly the reviewed table above.

    The oracle names all fifteen command groups the composition root registers
    plus their nested groups, and this asserts exact equality against the live
    tree — in both directions. A new UI operation cannot ship a CLI
    counterpart without it appearing here for a reviewer to see, and a CLI
    command cannot appear without someone deciding it belongs.

    It used to name five groups of the fifteen, which is why this could not
    fail on the ten it never mentioned. What it still cannot see on its own is
    a UI operation the CLI simply never grew — that is asserted separately, as
    the named exemptions in ``_KNOWN_PARITY_GAPS``, so US4's claim is bounded
    rather than assumed.
    """
    root = _subcommands("")
    top_level = {path for path in _EXPECTED_GROUPS if " " not in path}
    assert root == top_level, (
        f"top-level command groups drifted: "
        f"registered-but-untabled={sorted(root - top_level)}, "
        f"tabled-but-missing={sorted(top_level - root)}"
    )

    for path, expected in _EXPECTED_GROUPS.items():
        actual = _subcommands(path)
        assert actual == expected, (
            f"'{path}' subcommands drifted: "
            f"registered-but-untabled={sorted(actual - expected)}, "
            f"tabled-but-missing={sorted(expected - actual)}"
        )

    for path, expected_opts in _OPTION_ONLY_GROUPS.items():
        assert expected_opts <= _long_options(path), (
            f"'{path}' is missing options {sorted(expected_opts - _long_options(path))}"
        )


def test_the_known_parity_gaps_are_still_gaps():
    """Each exemption in ``_KNOWN_PARITY_GAPS`` is still missing.

    An exemption that outlives its gap is worse than no exemption at all: it
    goes on telling a reader the CLI cannot do something it can. So each one is
    asserted from the absent side. When a gap is closed this test reds, and the
    fix is to add the new subcommand to ``_EXPECTED_GROUPS`` and delete the
    entry here.
    """
    assert set(_KNOWN_PARITY_GAPS) == {
        "agent model",
        "provider use-builtin",
        "memory files",
    }, "a parity gap was added or removed without updating the assertions below"

    # 1. `agent model` — nothing on the agent CLI binds a model.
    assert "model" not in _subcommands("agent"), _KNOWN_PARITY_GAPS["agent model"]
    for sub in ("add", "edit"):
        opts = _long_options(f"agent {sub}")
        assert "--model" not in opts, (
            f"`coffer agent {sub}` grew --model; the gap is closed — move it "
            f"into _EXPECTED_GROUPS/_OPTION_ONLY_GROUPS and drop the exemption"
        )

    # 2. `provider use-builtin` — the route's CLI counterpart does not exist.
    assert "use-builtin" not in _subcommands("provider"), _KNOWN_PARITY_GAPS["provider use-builtin"]

    # 3. `memory files` — no file browse or read under `coffer memory`.
    memory_subs = _subcommands("memory")
    file_reaching = {"files", "file", "ls", "cat", "read", "tree"} & memory_subs
    assert not file_reaching, (
        f"`coffer memory` grew {sorted(file_reaching)}; {_KNOWN_PARITY_GAPS['memory files']}"
    )


def test_every_command_group_renders_its_help():
    """`--help` must succeed for every group — an import-time or annotation
    error in one command module otherwise only surfaces when a user reaches
    for it."""
    for path in _EXPECTED_GROUPS:
        result = runner.invoke(app, [*path.split(), "--help"])
        assert result.exit_code == 0, f"{path} --help exited {result.exit_code}:\n{result.output}"


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="command line surfaces same errors",
)
def test_cli_surfaces_same_errors(tmp_path, monkeypatch):
    """The CLI's error output matches the UI's user-facing message.

    Drive a representative failure scenario (spawn timeout / daemon
    unreachable) through the CLI and verify:
    - No raw Python traceback leaks to the user.
    - The exit code is within the documented range (1-8).
    - A human-readable message is present on stderr or stdout.

    Detect-or-spawn: client_or_exit() now auto-spawns on missing daemon.json. We
    simulate a spawn-that-times-out so the DaemonNotRunning (exit 3) path
    is exercised.
    """
    import coffer.surfaces.cli._client as cli_client

    monkeypatch.setenv("HOME", str(tmp_path))
    # Prevent real daemon spawn; simulate timeout.
    monkeypatch.setattr(cli_client, "_spawn_daemon", lambda: None)
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 0.05)

    result = runner.invoke(app, ["mcp", "show", "nope"])

    combined = result.output + (result.stderr or "")

    # spawn timeout → daemon boot failed → exit 3
    assert result.exit_code == 3, f"unexpected exit code {result.exit_code}:\n{combined}"
    # The CLI must not expose a raw Python traceback to the user.
    assert "Traceback" not in combined, f"raw traceback leaked to user output:\n{combined}"
    # There must be some message output.
    assert combined.strip(), "no output produced on error"


# ---------------------------------------------------------------------------
# T2 — CLI error renderer + --verbose
# ---------------------------------------------------------------------------


def _fake_client_returning_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire CLI to a tiny in-process server that returns 500 for every request."""
    from datetime import UTC
    from datetime import datetime as dt

    err_app = FastAPI()

    @err_app.get("/api/v1/daemon/status")
    def boom() -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "kaboom", "details": {}}},
        )

    set_active_token("test-tok")
    fake = TestClient(
        err_app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": "test-tok"},
        raise_server_exceptions=False,
    )
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=8000,
        token="test-tok",
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake, info))


def _fake_client_returning_credential_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire CLI to a server that returns 400 CREDENTIAL_MISSING."""
    from datetime import UTC
    from datetime import datetime as dt

    err_app = FastAPI()

    @err_app.get("/api/v1/daemon/status")
    def cred_missing() -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "CREDENTIAL_MISSING",
                    "message": "credential not found: MY_TOKEN",
                    "details": {},
                }
            },
        )

    set_active_token("test-tok")
    fake = TestClient(
        err_app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": "test-tok"},
        raise_server_exceptions=False,
    )
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=8000,
        token="test-tok",
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake, info))


def test_cli_5xx_shows_actionable_message_not_traceback(monkeypatch):
    """A 5xx HTTP error must produce a user-readable message, not a traceback."""
    _fake_client_returning_500(monkeypatch)
    result = runner.invoke(app, ["daemon", "status"])
    combined = result.output + (result.stderr or "")
    assert result.exit_code != 0, f"expected non-zero exit, got 0:\n{combined}"
    assert "Traceback" not in combined, f"raw traceback leaked:\n{combined}"
    assert combined.strip(), "no output on error"


def test_cli_verbose_shows_trace(monkeypatch):
    """With --verbose, the error includes HTTP status/detail context."""
    _fake_client_returning_500(monkeypatch)
    result = runner.invoke(app, ["--verbose", "daemon", "status"])
    combined = result.output + (result.stderr or "")
    assert result.exit_code != 0, f"expected non-zero exit, got 0:\n{combined}"
    # --verbose must include extra context (the traceback text itself)
    assert "HTTPStatusError" in combined or "500" in combined, (
        f"--verbose output missing error context:\n{combined}"
    )


def test_cli_credential_missing_maps_to_exit_8(monkeypatch):
    """CREDENTIAL_MISSING error code must map to exit code 8."""
    _fake_client_returning_credential_missing(monkeypatch)
    result = runner.invoke(app, ["daemon", "status"])
    assert result.exit_code == 8, (
        f"expected exit code 8 (CREDENTIAL_ISSUE), got {result.exit_code}:\n{result.output}"
    )
