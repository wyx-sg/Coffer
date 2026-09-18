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
    # ``rename`` is here, on the KIND-AGNOSTIC group, because that is where
    # renaming now lives: the name is a label on every resource, so moving
    # it is one command for all nine kinds rather than a per-kind route
    # only ``provider`` ever grew (ADR resource-identity-is-an-immutable-uid).
    "resource": {"list", "show", "rename", "enable", "disable", "delete"},
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
    # Exactly FR-039's list and nothing beyond it. `grep` and `search` are
    # gone with the retrieval surface (spec knowledge FR-033) — the corpus is
    # plain Markdown under ~/.coffer/knowledge/, so a person's own grep beats
    # anything this group could wrap — and `organize` went with the tidy pass
    # `curate` replaces.
    "knowledge": {
        "collections",
        "create",
        "curate",
        "delete",
        "ls",
        "read",
        "upload",
        "write",
    },
    "memory": {
        "context",
        "delivery",
        "delivery-install",
        "delivery-remove",
        "distil",
        "ls",
        "note",
        "notes",
        "partitions",
        "read",
        "retired",
        "sync",
    },
    "provider": {
        "add",
        "edit",
        # No "rename": it moved to the kind-agnostic group, where it covers
        # every kind instead of this one.
        "rm",
        "list",
        "show",
        "key",
        "switch",
        "use-builtin",
        "internal-default",
        # The transcription flag is its OWN command for the reason it is its
        # own flag: a chat gateway commonly serves no transcription endpoint,
        # so there is no fallback from `internal-default` to fold it into.
        "transcribe-default",
    },
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
    # Coffer's own operating settings (spec internal-engine FR-020/FR-021):
    # the model its passes think with, and the switch and timer of each pass
    # it runs unattended. Listed here because `.agents/sdd.md` requires every
    # management operation to be reachable from a terminal, and one of these
    # passes rewrites the user's own knowledge files on a timer.
    "engine": {"model", "upkeep", "timeout", "transcribe-model"},
    "engine model": {"show", "set", "clear"},
    "engine upkeep": {"list", "set"},
    # The other two settings on the same singleton (spec internal-engine
    # FR-027). `timeout default` and `transcribe-model clear` are named
    # verbs rather than a null argument because a terminal has no way to spell
    # a JSON null, and the way back to the default is the half of each setting
    # an operator most needs.
    "engine timeout": {"show", "set", "default"},
    "engine transcribe-model": {"show", "set", "clear"},
}

#: The groups whose surface is options rather than subcommands. Each is
#: claimed by the long options a caller can pass, since an empty subcommand
#: set would otherwise assert nothing about them.
_OPTION_ONLY_GROUPS: dict[str, set[str]] = {
    "open": {"--json", "--no-browser"},
    # The model an agent answers with is a FIELD of the agent, so it is bound
    # by the verb that edits the agent rather than by a command of its own —
    # which means the subcommand oracle above cannot see it and this is the
    # only place that claims it. It mirrors PATCH /api/v1/agents/{uid}, whose
    # `model` / `fast_model` / `wire_api` the projector reads.
    "agent edit": {"--model", "--fast-model", "--clear-fast-model", "--wire-api"},
    # Same shape, one kind over: a connection's wire is a FIELD of the
    # connection, corrected on the verb that edits it. `PATCH
    # /api/v1/providers/{uid}` carries `protocol`, and the CLI could not send
    # it while its own help called the field immutable.
    "provider edit": {"--protocol", "--base-url", "--secret"},
}

#: There are NO exempted UI operations today. `_KNOWN_PARITY_GAPS` used to
#: live here, naming three: the per-agent model binding (now
#: `coffer agent edit --model`, claimed in `_OPTION_ONLY_GROUPS`), reverting a
#: wire to the agent's built-in login (now `coffer provider use-builtin`), and
#: browsing a memory partition's files (now `coffer memory ls` / `read`). Each
#: was asserted from the absent side, so closing it reddened this module and
#: forced the exemption out — which is exactly what happened.
#:
#: Two more were found the way the table could not find them — by reading a
#: route's callers rather than the CLI's tree — and closed rather than listed:
#: `coffer provider rename` and `coffer provider edit --protocol`. That is the
#: standing limitation of this module: it can prove the tree matches the table,
#: and it cannot see an operation the CLI never grew.
#:
#: `coffer provider rename` has since been REMOVED again, and its absence is
#: not a gap: renaming became a field on the kind-agnostic update, so
#: `coffer resource rename provider <name> <new>` serves it — and serves the
#: other eight kinds, which never had a rename at all.
#:
#: If a UI operation ever ships without a CLI counterpart again, write the
#: exemption back the same way: a name, the reason, and an assertion that the
#: command is STILL missing, so that filling the gap cannot leave a stale
#: exemption telling readers the CLI cannot do something it can.


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
    spec="resource-framework",
    scenario="command line covers every visual operation",
)
def test_cli_covers_every_visual_operation():
    """The CLI's command tree is exactly the reviewed table above.

    The oracle names all sixteen command groups the composition root registers
    plus their nested groups, and this asserts exact equality against the live
    tree — in both directions. A new UI operation cannot ship a CLI
    counterpart without it appearing here for a reviewer to see, and a CLI
    command cannot appear without someone deciding it belongs.

    It used to name five groups of the sixteen, which is why this could not
    fail on the ones it never mentioned. What it still cannot see on its own is
    a UI operation the CLI simply never grew: that was carried as a table of
    named exemptions, each asserted from the absent side, and all three are now
    closed — see the note above ``_subcommands`` for how to write one back.
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


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="command line covers every visual operation",
)
def test_every_command_group_renders_its_help():
    """`--help` must succeed for every group — an import-time or annotation
    error in one command module otherwise only surfaces when a user reaches
    for it."""
    for path in _EXPECTED_GROUPS:
        result = runner.invoke(app, [*path.split(), "--help"])
        assert result.exit_code == 0, f"{path} --help exited {result.exit_code}:\n{result.output}"


@pytest.mark.acceptance(
    spec="resource-framework",
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
