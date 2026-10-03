"""REST/CLI parity (spec resource-framework "Reach every management operation
from both REST and the CLI").

- The live command tree is exactly the reviewed table below, in both directions.
- Every ``coffer config`` key is paired with the route (or pre-bind file) that
  stores it, and every settings route is claimed by a key.
- Every REST route that serves a plain file to the web UI is listed, paired with
  the ``coffer path`` target that names the same files.
- The CLI surfaces errors in the same human-readable form as the UI.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli._config_keys import FAMILIES, static_settings
from coffer.surfaces.cli.main import app
from coffer.surfaces.http.auth import set_active_token

runner = CliRunner()

#: The lifecycle verbs one factory builds for every kind group from its
#: ``Kind`` descriptor (design D1). A kind that cannot support a verb omits it.
_LIFECYCLE = {"list", "show", "edit", "rm", "enable", "disable"}
#: The lifecycle verbs a non-toggleable kind (knowledge, memory) leaves out
#: (spec resource-framework "Address every resource by an immutable uid
#: through one kind-agnostic surface").
_SWITCH = {"enable", "disable"}


#: Every command group the CLI composition root registers, and every
#: subcommand each one registers, written down as an oracle. Asserted for
#: EXACT equality against the live command tree, in both directions: a UI
#: operation that ships without a CLI counterpart goes red here, and so does a
#: CLI command that appears without anyone deciding on it. Nested groups are
#: keyed by their full path ("mcp cap"), so a group's own subcommands are
#: covered too.
_EXPECTED_GROUPS: dict[str, set[str]] = {
    "migrate": set(),
    # The daemon's own lifecycle. Its port is the key `daemon.port`, changed
    # through `config` with no daemon running; the passes in flight are a
    # section of `status` (spec daemon "Manage the daemon from the command line").
    "daemon": {"start", "stop", "restart", "status", "rotate-token", "service"},
    # What starts the daemon at login (spec daemon "Run as a login service"),
    # reachable with no daemon running — the state "it was not running" is most
    # often diagnosed from. It also carries PUT /daemon/residency.
    "daemon service": {"install", "uninstall", "status"},
    # `coffer open` is the one group with NO subcommands: a single action
    # (open the UI at the running daemon's origin) expressed as an
    # invoke_without_command callback. Its surface is its options, which
    # _OPTION_ONLY_GROUPS asserts instead — a narrowed claim, not a hole.
    "open": set(),
    # Every setting through one key registry (spec resource-framework "Change
    # every setting through one key-value command"); the keys themselves are
    # the _CONFIG_KEYS table below.
    "config": {"list", "get", "set", "unset"},
    # The three records the Activity page shows, from the same routes, plus
    # the on-demand prune (spec resource-framework "Read the audit log from
    # the command line").
    "log": {"audit", "mcp", "daemon", "prune"},
    # Plain files are read and edited with the caller's own tools; this names
    # them (spec resource-framework "Locate file-backed state with coffer
    # path"). Its targets answer the _FILE_BACKED_ROUTES below.
    "path": {"knowledge", "memory", "skill", "agent", "logs", "vault"},
    # What an agent holds that Coffer does not manage yet (spec
    # resource-framework "Scan, adopt and discard what Coffer does not
    # manage"): `scan` is a single command; adopt/discard take the row's kind.
    # Neither offers `agent`: a detected agent is registered with `agent add`,
    # which its scan row names, and nothing of Coffer's put it there to discard.
    "scan": set(),
    # `coffer run [--secret …] -- cmd`: one command, standalone secrets set
    # only in the child's environment (spec secret "Resolve standalone
    # secrets into one child with coffer run").
    "run": set(),
    "adopt": {"skill", "mcp"},
    "discard": {"skill", "mcp"},
    # `test` re-queries capabilities, then reports health; `prompt` prints the
    # hand-off a server's page offers; `cap` toggles one tool, prompt or
    # resource and sets how a tool is exposed (spec mcp-gateway).
    "mcp": {*_LIFECYCLE, "add", "scope", "test", "handoff", "cap"},
    "mcp cap": {"list", "enable", "disable", "expose"},
    # Custom-tool groups (spec mcp-gateway "Manage custom tools on REST and the
    # command line"): an `mcp_server` of the `http_api` transport. `reimport`
    # previews then applies an OpenAPI re-read; `op` manages one tool.
    "tool": {*_LIFECYCLE, "add", "scope", "reimport", "op"},
    "tool op": {"add", "edit", "rm", "enable", "disable", "scope", "test"},
    # `get` checks presence only; no command prints a value (spec secret
    # "Return no plaintext on any route, command or tool"). `approvals` and
    # `reject` are the terminal's half of the approvals the desktop app
    # approves; `scan` and `import` move plaintext secret files into the store.
    "secret": {"set", "get", "list", "rm", "approvals", "reject", "scan", "import"},
    # No `scope`: an agent is not reached by agents. `connect`/`disconnect`
    # are its Coffer connection — the gateway entry and the memory hook as one
    # action (spec agent-registry "Connect an agent to Coffer in one action"),
    # whose status `show` prints as `coffer_connection`; `transcript [<id>]` reads
    # the agent's history; `models` is the web model picker's list
    # (GET /agent-providers/{agent_key}/models); `hooks` lists every hook in
    # the agent's native config (GET /agents/{uid}/hooks); `prompt` prints the
    # install prompt GET /agents/types and GET /agents/{uid} carry as
    # `install_handoff`.
    "agent": {
        *_LIFECYCLE,
        "add",
        "connect",
        "disconnect",
        "transcript",
        "models",
        "config",
        "plugin",
        "hooks",
        "prompt",
    },
    # Writes to the agent's own config files; reading them is `path agent
    # <name> config` (see _FILE_BACKED_ROUTES).
    "agent config": {"edit", "rm"},
    "agent plugin": {"list", "show", "enable", "disable", "rm"},
    # `edit` carries the group-gating switches; `pair`, `bind` and `notify`
    # are the channel's own acts (spec channels); `restart` is the explicit
    # reconnect of a channel's adapter.
    "channel": {*_LIFECYCLE, "add", "scope", "pair", "unpair", "bind", "notify", "restart"},
    # Exactly spec skill-manager "Cover skill management on REST, the CLI and
    # the web": `add <folder>` is the import, and the master folder is named
    # by `path skill <name>` rather than listed, printed or written here.
    # A skill has nothing editable: its name is fixed and it carries no title.
    # `add` also takes an archive or a Git URL, and `update` is a Git-imported
    # skill's upstream updates (check, preview, apply, keep mine).
    "skill": {*_LIFECYCLE - {"edit"}, "add", "update", "scope", "verify"},
    # The commands skills require (spec skill-manager "Serve required commands
    # on REST, the command line and the web"): read, probe again, and print
    # the hand-off prompt for the person's agent; `add`, `edit` and `rm`
    # declare a tool by hand, with no skill (spec skill-manager "Declare a
    # command-line tool without a skill").
    "cli": {"list", "show", "check", "prompt", "add", "edit", "rm"},
    # Exactly spec knowledge "Cover knowledge management on REST and the
    # CLI". Documents are listed, read, edited and deleted on disk under
    # `path knowledge`. A collection
    # has no `scope` and no switch (spec knowledge "Serve every collection to
    # every agent"), so no `enable`/`disable`.
    # `history`, `restore`, `changes` and `undo` read and reverse a
    # collection's git history (spec knowledge "Keep every document's history
    # and undo a pass as a whole", "Follow knowledge changes across collections").
    "knowledge": {
        *_LIFECYCLE - _SWITCH,
        "add",
        "write",
        "upload",
        "curate",
        "history",
        "restore",
        "changes",
        "undo",
    },
    # No `add`: partitions are provisioned only by aggregation. `sync` updates
    # memory — aggregation, then a distil pass over every partition that
    # gained entries (spec memory "Update memory in one action"). `hook` is
    # what every installed memory hook entry runs and must not move (spec
    # memory "Cover memory management on REST and the CLI"); installing those
    # entries is part of `agent connect`. `trigger` manages the authored guards in
    # vault/memory-triggers/; `delivered` prints the delivery views. No switch
    # either (spec memory "Serve every partition to every agent").
    "memory": {*_LIFECYCLE - _SWITCH, "sync", "hook", "delivered", "trigger"},
    "memory trigger": {"list", "add", "arm", "disarm", "delete"},
    # `builtin` reverts a wire to the agent's own login; the two flags a
    # connection can carry are the keys `engine.provider` and
    # `transcribe.provider`, not commands here.
    "provider": {
        *_LIFECYCLE,
        "add",
        "scope",
        "switch",
        "builtin",
        "detect-local",
        "order",
        "price",
    },
    # A round stops on any conflict and is answered here file by file
    # (ADR sync-applies-clean-merges-and-stops-on-any-conflict); `status`
    # includes the remote (spec vault-sync).
    "sync": {
        "choose",
        "conflicts",
        "continue",
        "edit",
        "history",
        "hold",
        "join",
        "key",
        "machine",
        "now",
        "push-anyway",
        "remote",
        "resolve",
        "rollback",
        "status",
    },
    # No `export`: a key backup is written only by the desktop app, behind a
    # presence check (spec secret "Release plaintext only to a present
    # human in the desktop app").
    "sync key": {"import", "fingerprint"},
    # The unified reconciler's read models (spec resource-framework "Converge
    # what Coffer writes outside its database with one reconciler"): `list` is
    # GET /reconcile/plan, `repair` is POST /reconcile/apply.
    "drift": {"list", "repair"},
    # GET /attention: the Overview's "needs you" list — a single command.
    "attention": set(),
    # The Usage page (ADR usage-is-metered-at-the-proxy-and-subscriptions-show-
    # only-official-quota): the bare group is the summary (GET /usage/summary,
    # or /usage/export.csv with --csv); `requests` is GET /usage/requests;
    "usage": {"requests"},
    # The local model proxy (spec provider-switching "Authenticate each agent
    # to the proxy with its own local token"): `token` is GET
    # /proxy/tokens/{uid} — what both agents' projected config runs — `rotate`
    # is POST /proxy/tokens/{uid}/rotate, `status` is GET /proxy/status.
    "proxy": {"token", "rotate", "status"},
    "sync machine": {"list", "rename", "rm"},
    "sync remote": {"set", "clear", "pause", "resume", "check"},
    # Any vault file's history (spec vault-storage "Show, compare and restore
    # any version of a vault file"): GET /vault/history, /vault/diff,
    # /vault/content, POST /vault/restore, and GET /vault/problems — the hand
    # edits validation kept out of HEAD.
    "vault": {"history", "diff", "show", "restore", "problems"},
}

#: The groups whose surface is options rather than subcommands. Each is
#: claimed by the long options a caller can pass, since an empty subcommand
#: set would otherwise assert nothing about them.
_OPTION_ONLY_GROUPS: dict[str, set[str]] = {
    # The one-time upgrade into the vault layout (spec vault-storage).
    "migrate": {"--rollback", "--resume", "--rehearse", "--home"},
    "open": {"--json", "--no-browser"},
    # --ref shows one row in full: a direct MCP entry (spec agent-registry "Show
    # one direct MCP entry's full configuration without its secrets") or an
    # unmanaged skill (spec skill-manager "Preview an unmanaged skill read-only").
    "scan": {"--agent", "--ref", "--source", "--json"},
    "attention": {"--json"},
    "run": {"--secret", "--env-file", "--no-masking"},
    # The usage summary's range, grouping, filters and output form.
    "usage": {"--range", "--from", "--to", "--by", "--agent", "--provider", "--json", "--csv"},
    # A name and a title are edited on the kinds that carry them (design D1).
    # A collection is named by its folder: a name and a description, no title.
    "knowledge edit": {"--name", "--description"},
    # The model an agent answers with is a FIELD of the agent, bound by the
    # verb that edits the agent. It mirrors PATCH /api/v1/agents/{uid}, whose
    # `model` / `effort` / `tier_models` the projector reads. Its
    # config directory is the one other thing an agent's edit changes.
    "agent edit": {
        "--config-dir",
        "--model",
        "--effort",
        "--clear-effort",
        "--tier",
        "--clear-tiers",
    },
    # A connection's wire is a FIELD of the connection, corrected on the verb
    # that edits it: PATCH /api/v1/providers/{uid} carries `protocol`.
    "provider edit": {"--protocol", "--base-url", "--secret", "--title"},
    # An MCP server's config as the web UI's edit dialog changes it, spelled
    # the way `mcp add` spells it (spec mcp-gateway).
    "mcp edit": {
        "--stdio",
        "--http",
        "--env",
        "--header",
        "--secret",
        "--spawn-timeout-seconds",
        "--request-timeout-seconds",
    },
    # The group-gating switches of a channel (spec channels).
    "channel edit": {"--require-mention", "--ignore-other-mentions", "--title"},
}

#: The edit verbs of the kinds that carry no title (agent, mcp_server).
_UNTITLED_EDITS = ("agent edit", "mcp edit")

#: Every `coffer config` key, paired with where the setting is stored: the
#: route the key writes through, or the pre-bind settings file for the one key
#: read before the daemon binds. `<key>` and `<table>` stand for a family the
#: daemon enumerates (the registered features, the prunable tables).
_CONFIG_KEYS: dict[str, str] = {
    "daemon.port": "~/.coffer/daemon-config.json",
    "engine.provider": "POST /providers/{uid}/internal-default",
    "engine.model": "PUT /internal-engine-config",
    "engine.timeout": "PUT /internal-engine-config/timeout",
    "engine.curate_owner": "PUT /internal-engine-config/curation-owner",
    **{
        f"engine.upkeep.{name}.{field}": "PUT /internal-engine-config/upkeep"
        for name in ("aggregate", "distil", "curate")
        for field in ("enabled", "interval")
    },
    "transcribe.provider": "POST /providers/{uid}/transcribe-default",
    "transcribe.model": "PUT /internal-engine-config/transcribe-model",
    "secrets.storage": "PUT /settings/secrets",
    # Turning it off waits for the Coffer app (spec secret "Turn the
    # protection off only through the desktop app").
    "secrets.require_approval": "PUT /settings/secret-boundary",
    "prices.refresh": "PUT /providers/price-list",
    "feature.<key>": "PUT /daemon/features/{key}",
    "retention.<table>": "PATCH /retention/policies/{table_name}",
}

#: Settings routes a key reaches without naming them as its store — the
#: `unset` of a family whose default lives on the daemon — and the one
#: settings route that is not a key at all.
_SETTINGS_ROUTES_ELSEWHERE: dict[str, str] = {
    "DELETE /daemon/features/{key}": "config unset feature.<key>",
    "PUT /daemon/residency": "daemon service install|uninstall",
}

#: Where a write to Coffer's settings lives in the management API. A write
#: route under one of these that no key or entry above claims fails the test.
_SETTINGS_ROUTE = re.compile(
    r"^(PUT|PATCH|POST|DELETE) /(internal-engine-config|settings/|daemon/features|"
    r"daemon/residency|retention/policies|providers/\{uid\}/[a-z-]+-default)"
)

#: Every REST route that serves or writes a plain file for the web UI,
#: paired with the `coffer path` target that names the same files. The CLI
#: answers these by naming the file — a person or agent then reads and edits
#: it with their own tools — rather than by a command that prints it.
_FILE_BACKED_ROUTES: dict[str, str] = {
    "GET /knowledge/tree": "path knowledge [<collection>]",
    "GET /knowledge/file": "path knowledge <collection>",
    # The web UI's editor saves through it; on the command line a document is
    # edited on disk like any other file (spec knowledge "Cover knowledge
    # management on REST and the CLI").
    "PUT /knowledge/file": "path knowledge <collection>",
    "DELETE /knowledge/file": "path knowledge <collection>",
    "GET /memory/partitions/{uid}/files": "path memory <partition>",
    "GET /memory/partitions/{uid}/notes": "path memory <partition>",
    "GET /memory/partitions/{uid}/notes/{slug}": "path memory <partition>",
    "GET /memory/partitions/{uid}/retired": "path memory <partition>",
    "GET /skills/{uid}/files": "path skill <name>",
    "GET /skills/{uid}/files/content": "path skill <name>",
    "PUT /skills/{uid}/files/content": "path skill <name>",
    # An orphan folder sits in the vault's skills store under its own name
    # (spec skill-manager "Act on a folder in the skills store that no skill claims").
    "GET /skills/orphans/{name}/files": "path vault",
    "GET /skills/orphans/{name}/files/content": "path vault",
    "GET /agents/{uid}/config-files": "path agent <name> config",
    "GET /agents/{uid}/config-files/{key}": "path agent <name> config",
    "GET /agents/{uid}/config-files/{key}/files/{relpath}": "path agent <name> config",
    "GET /agents/{uid}/native-memory": "path agent <name> memory",
    "GET /agents/{uid}/native-memory/files": "path agent <name> memory",
    "GET /agents/{uid}/native-memory/files/content": "path agent <name> memory",
    # An unmanaged skill folder is named by the scan row that lists it
    # (spec skill-manager "Preview an unmanaged skill read-only").
    "GET /agents/{uid}/unmanaged-skills/{skill}/files": "scan --agent <name>",
    "GET /agents/{uid}/unmanaged-skills/{skill}/files/content": "scan --agent <name>",
}

#: File-shaped routes that are NOT answered by `coffer path`, because they
#: change a file through validation and a fingerprint check a text editor
#: would skip (spec agent-registry "Reject stale config-file writes by
#: fingerprint").
_FILE_ROUTES_WITH_A_COMMAND: dict[str, str] = {
    "PUT /agents/{uid}/config-files/{key}": "agent config edit",
    "PUT /agents/{uid}/config-files/{key}/files/{relpath}": "agent config edit",
    "DELETE /agents/{uid}/config-files/{key}/files/{relpath}": "agent config rm",
    # A stopped sync round's files: answered and hand-merged from the CLI too.
    "POST /sync/stop/files/answer": "sync resolve",
    "POST /sync/stop/files/editor": "sync edit",
    "POST /sync/stop/files/discard": "sync edit",
    "GET /sync/stop/files/versions": "sync conflicts",
    # A plugin's skill folder lives in the plugin cache; `agent plugin show`
    # says where, and its files are read with ordinary file tools.
    "GET /agents/{uid}/plugins/{plugin_id}/skills/{skill}/files": "agent plugin show",
    "GET /agents/{uid}/plugins/{plugin_id}/skills/{skill}/files/content": "agent plugin show",
}

#: What makes a route file-backed: a path segment naming a file, a tree of
#: files, or the Markdown files a memory partition is made of.
_FILE_SHAPED = re.compile(r"/(files?|tree|notes|retired|native-memory|config-files)(/|$)")


def _node(path: str) -> Any:
    from typer.main import get_command

    node: Any = get_command(app)
    for part in path.split():
        commands = getattr(node, "commands", {})
        assert part in commands, f"no command '{part}' under '{path}'"
        node = commands[part]
    return node


def _subcommands(path: str) -> set[str]:
    """The subcommand names registered under `path` in the live command tree.

    Read off the click tree rather than scraped out of ``--help``: the help is
    Rich-rendered into a width-dependent table, so a long name can wrap or be
    elided and a substring check would then pass or fail for reasons that have
    nothing to do with parity.
    """
    return set(getattr(_node(path), "commands", {}))


def _long_options(path: str) -> set[str]:
    """Every long option flag declared on the command at `path`."""
    return {
        opt
        for param in getattr(_node(path), "params", [])
        for opt in (*getattr(param, "opts", []), *getattr(param, "secondary_opts", []))
        if opt.startswith("--")
    }


def _api_routes() -> set[str]:
    """Every `METHOD /path` the management API serves, relative to /api/v1."""
    from coffer.surfaces.http.app import create_app

    paths = create_app().openapi()["paths"]
    return {
        f"{method.upper()} {path.removeprefix('/api/v1')}"
        for path, ops in paths.items()
        if path.startswith("/api/v1/")
        for method in ops
    }


@pytest.fixture(scope="module")
def api_routes(tmp_path_factory: pytest.TempPathFactory) -> Iterator[set[str]]:
    mp = pytest.MonkeyPatch()
    home = tmp_path_factory.mktemp("parity-home")
    mp.setenv("HOME", str(home))
    mp.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{home / 'c.db'}")
    try:
        yield _api_routes()
    finally:
        mp.undo()


@pytest.mark.acceptance(spec="vault-sync", scenario="the command line covers every sync operation")
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="command line covers every visual operation",
)
def test_cli_covers_every_visual_operation():
    """The CLI's command tree is exactly the reviewed table above.

    The oracle names all nineteen top-level commands the composition root
    registers plus their nested groups, and this asserts exact equality
    against the live tree — in both directions. A new UI operation cannot
    ship a CLI counterpart without it appearing here for a reviewer to see,
    and a CLI command cannot appear without someone deciding it belongs.

    What it cannot see on its own is a UI operation the CLI simply never
    grew. If one ever ships without a CLI counterpart, write the exemption
    down here: a name, the reason, and an assertion that the command is STILL
    missing, so filling the gap cannot leave a stale exemption behind.
    """
    root = _subcommands("")
    top_level = {path for path in _EXPECTED_GROUPS if " " not in path}
    assert root == top_level, (
        f"top-level commands drifted: "
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
    # The kinds without a title offer no way to set one, and an agent's name
    # is its type's.
    for path in _UNTITLED_EDITS:
        assert "--title" not in _long_options(path), f"'{path}' offers --title"
    assert not {"--name", "--description"} & _long_options("agent edit")

    # Machine-readable output for scripting: every list and show verb, every
    # kind group's alike.
    for path in _EXPECTED_GROUPS:
        for verb in {"list", "show"} & _subcommands(path):
            assert "--json" in _long_options(f"{path} {verb}"), f"'{path} {verb}' has no --json"


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="command line covers every visual operation",
)
def test_every_config_key_is_paired_with_the_route_that_stores_it(api_routes: set[str]):
    """The key registry is exactly `_CONFIG_KEYS`, each key stored where the
    table says; and every settings route the API serves is some key's store
    (or is named in `_SETTINGS_ROUTES_ELSEWHERE`), so a settings route with no
    key fails here."""

    class _Stub:
        """Answers a family's enumeration with one member each."""

        def get(self, path: str) -> dict[str, Any]:
            return {
                "/daemon/features": {
                    "features": [{"key": "<key>", "enabled": True, "source": "channel"}]
                },
                "/retention/policies": {
                    "policies": [
                        {
                            "table_name": "<table>",
                            "display_name": "T",
                            "retention_days": 1,
                            "default_retention_days": 1,
                        }
                    ]
                },
            }[path]

    live = {s.key: s.store for s in static_settings()}
    for family in FAMILIES:
        live |= {m.key: m.store for m in family.members(_Stub())}  # type: ignore[arg-type]
    live = {
        k: v.replace("/<key>", "/{key}").replace("/<table>", "/{table_name}")
        for k, v in live.items()
    }
    assert live == _CONFIG_KEYS

    stores = {v for v in _CONFIG_KEYS.values() if not v.startswith("~")}
    assert stores <= api_routes, f"stores the API no longer serves: {sorted(stores - api_routes)}"
    elsewhere = set(_SETTINGS_ROUTES_ELSEWHERE)
    assert elsewhere <= api_routes, f"stale entries: {sorted(elsewhere - api_routes)}"

    settings_routes = {r for r in api_routes if _SETTINGS_ROUTE.match(r)}
    unclaimed = settings_routes - stores - elsewhere
    assert not unclaimed, f"settings routes no config key claims: {sorted(unclaimed)}"


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="file-backed reads are answered by coffer path",
)
def test_file_backed_routes_are_answered_by_coffer_path(api_routes: set[str]):
    """Every file-shaped route the API serves is either listed in
    `_FILE_BACKED_ROUTES` with a live `coffer path` target, or has a command
    of its own in `_FILE_ROUTES_WITH_A_COMMAND` — in both directions, so a new
    file route and a listed route the API dropped both fail here."""
    file_shaped = {r for r in api_routes if _FILE_SHAPED.search(r.split(" ", 1)[1])}
    listed = set(_FILE_BACKED_ROUTES) | set(_FILE_ROUTES_WITH_A_COMMAND)
    assert file_shaped == listed, (
        f"file-backed routes drifted: "
        f"served-but-unlisted={sorted(file_shaped - listed)}, "
        f"listed-but-not-served={sorted(listed - file_shaped)}"
    )

    for route, target in _FILE_BACKED_ROUTES.items():
        words = target.split()
        if words[0] == "scan":
            # `coffer scan` is option-only; its rows carry each folder's path.
            assert "scan" in _subcommands(""), (route, target)
            continue
        assert words[0] == "path" and words[1] in _subcommands("path"), (route, target)
    for route, command in _FILE_ROUTES_WITH_A_COMMAND.items():
        group, verb = command.rsplit(" ", 1)
        assert verb in _subcommands(group), (route, command)


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="command line covers every visual operation",
)
def test_every_command_group_renders_its_help():
    """`--help` must succeed for every group — an import-time or annotation
    error in one command module otherwise only surfaces when a user reaches
    for it."""
    for path in ["", *_EXPECTED_GROUPS]:
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
# CLI error renderer + --verbose
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
    monkeypatch.setattr(_cli_client, "daemon_is_running", lambda: True)


def _fake_client_returning_secret_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire CLI to a server that returns 400 SECRET_MISSING."""
    from datetime import UTC
    from datetime import datetime as dt

    err_app = FastAPI()

    @err_app.get("/api/v1/daemon/status")
    def cred_missing() -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "SECRET_MISSING",
                    "message": "secret not found: MY_TOKEN",
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
    monkeypatch.setattr(_cli_client, "daemon_is_running", lambda: True)


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


def test_cli_secret_missing_maps_to_exit_8(monkeypatch):
    """SECRET_MISSING error code must map to exit code 8."""
    _fake_client_returning_secret_missing(monkeypatch)
    result = runner.invoke(app, ["daemon", "status"])
    assert result.exit_code == 8, (
        f"expected exit code 8 (SECRET_ISSUE), got {result.exit_code}:\n{result.output}"
    )
