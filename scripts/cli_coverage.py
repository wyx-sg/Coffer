# ruff: noqa: RUF001 — the Chinese page's own words use full-width punctuation.
#!/usr/bin/env python3
"""Does the command line offer every operation the web UI and the desktop app do?

Spec resource-framework "Offer every management operation on the command
line"; design align-cli-with-ui-and-add-tool-environments D2.

Reads, from the source itself:

* every ``(method, route)`` the web UI calls through its typed client
  (``getApiClient().GET("/agents/{uid}", ...)`` in ``frontend/src``, tests left
  out);
* every IPC command the desktop shell exposes (``generate_handler![...]`` in
  ``desktop/src/lib.rs``);
* the CLI's registry (``coffer.surfaces.cli.registry``).

and fails when a UI route has no command and no recorded exemption, when an
exemption names a route the UI no longer calls, or when a shell command has no
command and no reason. ``--write`` renders the coverage table into
``docs-site/reference/cli-coverage.md`` and its Chinese twin; ``--check`` (what
``make lint`` runs) also fails when those pages are stale.

    .venv/bin/python scripts/cli_coverage.py --check
    .venv/bin/python scripts/cli_coverage.py --write
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

FRONTEND = REPO_ROOT / "frontend" / "src"
SHELL_LIB = REPO_ROOT / "desktop" / "src" / "lib.rs"
PAGES = {
    "en": REPO_ROOT / "docs-site" / "reference" / "cli-coverage.md",
    "zh": REPO_ROOT / "docs-site" / "zh" / "reference" / "cli-coverage.md",
}

_CALL = re.compile(r"\.(GET|POST|PUT|PATCH|DELETE)\(\s*\"(/[^\"]*)\"", re.DOTALL)
# A template-literal route, plus the ``as "..." | "..."`` cast that may follow it.
_TEMPLATE_CALL = re.compile(
    r"\.(GET|POST|PUT|PATCH|DELETE)\(\s*`(/[^`]*)`"
    r"(\s+as\s+(?:\|?\s*\"/[^\"]*\"\s*)+)?",
    re.DOTALL,
)
_HOLE = re.compile(r"\$\{([^}]*)\}")
_QUOTED = re.compile(r"\"([^\"]*)\"")
# ``fetch(`${base}/events`, { method: "GET" ...})``: the stream the page reads by fetch.
_FETCH = re.compile(r"\bfetch\(\s*`\$\{[^}]*\}(/[^`$]*)`(.{0,200})", re.DOTALL)
_METHOD = re.compile(r"method:\s*\"(GET|POST|PUT|PATCH|DELETE)\"")
_HANDLER = re.compile(r"generate_handler!\[(.*?)\]", re.DOTALL)


#: Routes the UI reads outside its typed client, each with why it has no command.
#: Local to this gate: they are not management operations, so they are not in the
#: registry's EXEMPT (which feeds the published coverage table).
STREAM_EXEMPT: dict[tuple[str, str], str] = {
    ("GET", "/events"): (
        "the page's live event stream (server-sent events): stream plumbing that "
        "refreshes views, not a management action"
    ),
}

#: Commands that stay hidden on purpose, each with why; every other command must be
#: reachable from visible help.
HIDDEN_ALLOWLIST: dict[str, str] = {
    "proxy token": "run by the agent shim to mint a per-agent token (proxy_cmd.py)",
}

STATIC_NOTE = (
    "static route/visibility check only: it compares route identities and help "
    "visibility; it is not an end-to-end test and does not check option or body semantics"
)


def _expand_template(route: str, cast: str | None) -> set[str]:
    """Concrete routes for a template-literal route (holes become ``{param}``)."""
    if cast:
        return set(_QUOTED.findall(cast))
    holes = list(_HOLE.finditer(route))
    options: list[list[str]] = []
    for hole in holes:
        words = _QUOTED.findall(hole.group(1))
        options.append(words if "?" in hole.group(1) and len(words) >= 2 else ["{param}"])
    routes = {route}
    for hole, words in zip(holes, options, strict=True):
        routes = {r.replace(hole.group(0), w, 1) for r in routes for w in words}
    return routes


def scan_routes(text: str) -> set[tuple[str, str]]:
    """Every ``(method, route)`` one source file's text calls: literal, template, fetch."""
    found = {(m, r) for m, r in _CALL.findall(text)}
    for method, route, cast in _TEMPLATE_CALL.findall(text):
        found |= {(method, r) for r in _expand_template(route, cast or None)}
    for route, tail in _FETCH.findall(text):
        found.add(((_METHOD.search(tail) or [None, "GET"])[1], route))
    return found


def frontend_routes() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in FRONTEND.rglob("*.ts*"):
        if ".test." in path.name or path.parts[-2] == "generated" or "/test/" in path.as_posix():
            continue
        found |= scan_routes(path.read_text(encoding="utf-8"))
    return found


def shell_commands() -> list[str]:
    block = _HANDLER.search(SHELL_LIB.read_text(encoding="utf-8"))
    assert block, "no generate_handler! in desktop/src/lib.rs"
    return [
        line.strip().rstrip(",").split("::")[-1]
        for line in block.group(1).split("\n")
        if "::" in line
    ]


def _registry():  # type: ignore[no-untyped-def]
    from coffer.surfaces.cli import (
        main,  # noqa: F401  (loads every command module)
        registry,
    )

    return registry


def _command_paths(reg):  # type: ignore[no-untyped-def]
    from coffer.surfaces.cli.command_reasons import COMMAND_REASONS

    return sorted({o.command for o in reg.OPERATIONS} | set(COMMAND_REASONS))


def visibility(
    root: Any, commands: Iterable[str], allowlist: dict[str, str]
) -> tuple[list[str], int, int]:
    """Problems, visible count and allow-listed hidden count for ``commands``.

    A command is visible when neither it nor any group above it is hidden.
    """
    out: list[str] = []
    visible = allowed = 0
    for command in commands:
        node, hidden, found = root, False, True
        for word in command.split(" "):
            node = (getattr(node, "commands", None) or {}).get(word)
            if node is None:
                found = False
                break
            hidden = hidden or bool(node.hidden)
        if not found:
            out.append(f"command {command}: not in the command tree")
        elif hidden and command in allowlist:
            allowed += 1
        elif hidden:
            out.append(
                f"command {command}: hidden from help (a hidden group or command); make it "
                "visible or add it to HIDDEN_ALLOWLIST with a reason"
            )
        elif command in allowlist:
            out.append(f"command {command}: in HIDDEN_ALLOWLIST but not hidden (drop the entry)")
        else:
            visible += 1
    for command in sorted(set(allowlist) - set(commands)):
        out.append(f"command {command}: in HIDDEN_ALLOWLIST but not a registered command")
    return out, visible, allowed


def _root_command() -> Any:
    import typer.main

    from coffer.surfaces.cli.main import app

    return typer.main.get_command(app)


def problems() -> list[str]:
    return _audit()[0]


def _audit() -> tuple[list[str], dict[str, int]]:
    reg = _registry()
    covered = {(o.method, o.route) for o in reg.OPERATIONS}
    ui = frontend_routes()
    exempt = set(reg.EXEMPT) | set(STREAM_EXEMPT)
    out: list[str] = []
    for method, route in sorted(ui - covered - exempt):
        out.append(
            f"{method} {route}: the web UI calls it and no command does (add one, or an EXEMPT row)"
        )
    for method, route in sorted(exempt - ui):
        out.append(f"{method} {route}: exempt, but the web UI no longer calls it (drop the row)")
    for method, route in sorted(exempt & covered):
        out.append(f"{method} {route}: exempt and covered at once (drop the exemption)")
    for name in shell_commands():
        if name not in reg.SHELL_COMMANDS:
            out.append(f"desktop command {name}: no command and no reason in SHELL_COMMANDS")
    for name in sorted(set(reg.SHELL_COMMANDS) - set(shell_commands())):
        out.append(f"desktop command {name}: in SHELL_COMMANDS but the shell no longer has it")
    from coffer.surfaces.cli.command_reasons import COMMAND_REASONS

    commands = {o.command for o in reg.OPERATIONS} | set(COMMAND_REASONS)
    for name, mapped in reg.SHELL_COMMANDS.items():
        if isinstance(mapped, str) and mapped not in commands:
            out.append(f"desktop command {name}: maps to {mapped!r}, which records no operation")
    commands = _command_paths(reg)
    seen, visible, allowed = visibility(_root_command(), commands, HIDDEN_ALLOWLIST)
    out += seen
    stats = {
        "ui": len(ui),
        "mapped": len(ui & covered),
        "exempt": len(ui & exempt),
        "missing": len(ui - covered - exempt),
        "commands": len(commands),
        "visible": visible,
        "allowlisted": allowed,
    }
    return out, stats


def summary(stats: dict[str, int]) -> str:
    return (
        f"cli_coverage: frontend route identities {stats['ui']} (typed client incl. dynamic, "
        f"plus SSE): mapped {stats['mapped']}, exempted {stats['exempt']}, "
        f"missing {stats['missing']}; registry commands {stats['commands']}: "
        f"visible {stats['visible']}, hidden-allowlisted {stats['allowlisted']}.\n"
        f"cli_coverage: {STATIC_NOTE}."
    )


# --- the coverage table ----------------------------------------------------------

_TEXT = {
    "en": {
        "title": "CLI coverage",
        "description": (
            "Every web UI and desktop operation, the route it calls, its coffer command "
            "and the test that covers it."
        ),
        "intro": (
            "Every management operation a person does on a Coffer page or in the desktop app "
            "has a `coffer` command that calls the same route, so an agent can do it too. "
            "This table is generated from the CLI's registry; `make lint` fails when a route "
            "the web UI calls has no command."
        ),
        "head": "| UI operation | Route | Command | Acceptance |",
        "exempt": "## Without a command {#without-a-command}",
        "exempt_intro": (
            "Plain files are read and edited with your own tools, and a few acts only make sense "
            "at the window."
        ),
        "exempt_head": "| Route | Why |",
        "shell": "## Desktop app {#desktop-app}",
        "shell_head": "| Desktop command | Command |",
        "cat": {
            "file-content": "plain file",
            "window": "the window",
            "internal": "the page's plumbing",
        },
    },
    "zh": {
        "title": "CLI 覆盖表",
        "description": (
            "每一个网页界面和桌面应用操作、它调用的接口、对应的 coffer 命令和覆盖它的测试。"
        ),
        "intro": (
            "人在 Coffer 页面或桌面应用里能做的每一个管理操作，都有一个调用同一接口的 `coffer` "
            "命令，Agent 也能直接完成。本表由 CLI 的登记表生成；网页界面调用的接口没有命令时，"
            "`make lint` 会失败。"
        ),
        "head": "| 界面操作 | 接口 | 命令 | 验收 |",
        "exempt": "## 没有命令的操作 {#without-a-command}",
        "exempt_intro": "普通文件用你自己的工具读写；少数操作只在窗口前有意义。",
        "exempt_head": "| 接口 | 原因 |",
        "shell": "## 桌面应用 {#desktop-app}",
        "shell_head": "| 桌面命令 | 命令 |",
        "cat": {"file-content": "普通文件", "window": "窗口操作", "internal": "页面内部"},
    },
}

#: The test that covers each command, by its first words (longest match wins).
ACCEPTANCE = {
    "custom-tool": "test_custom_tool_cli.py",
    "approval": "test_approval_cli.py",
    "secret reveal": "test_approval_cli.py",
    "secret backup-key": "test_approval_cli.py",
    "app update": "test_approval_cli.py",
    "log": "test_log_cmd.py",
    "mcp test": "test_mcp_cmd.py",
    "cli list": "test_cli_list_cmd.py",
    "secret list": "test_secret_cmd.py",
    "secret set": "test_secret_cmd.py",
    "daemon status": "test_daemon_status_cmd.py",
    "vault problems": "test_vault_cmd.py",
    "sync wait": "test_cli_parity.py",
    "update": "test_lifecycle_cli.py",
    "uninstall": "test_lifecycle_cli.py",
}
_DECLARED = "test_cli_parity.py"


def _acceptance(command: str) -> str:
    best = max(
        (k for k in ACCEPTANCE if command == k or command.startswith(k + " ")),
        key=len,
        default=None,
    )
    return ACCEPTANCE[best] if best else _DECLARED


def render(locale: str) -> str:
    reg = _registry()
    t = _TEXT[locale]
    lines = [
        "---",
        f"title: {t['title']}",
        f"description: {t['description']}",
        "---",
        "",
        f"# {t['title']} {{#cli-coverage}}",
        "",
        t["intro"],
        "",
    ]
    by_group: dict[str, list] = defaultdict(list)  # type: ignore[type-arg]
    seen: set[tuple[str, str, str]] = set()
    for op in reg.OPERATIONS:
        key = (op.command, op.method, op.route)
        if key in seen:
            continue
        seen.add(key)
        by_group[op.command.split(" ")[0]].append(op)
    for group in sorted(by_group):
        lines += [f"## `coffer {group}` {{#{group}}}", "", t["head"], "| --- | --- | --- | --- |"]
        for op in sorted(by_group[group], key=lambda o: (o.command, o.route, o.method)):
            test = _acceptance(op.command)
            lines.append(
                f"| {op.ui} | `{op.method} {op.route}` | `coffer {op.command}` | `{test}` |"
            )
        lines.append("")
    lines += [t["exempt"], "", t["exempt_intro"], "", t["exempt_head"], "| --- | --- |"]
    for (method, route), (cat, why) in sorted(
        reg.EXEMPT.items(), key=lambda kv: (kv[0][1], kv[0][0])
    ):
        lines.append(f"| `{method} {route}` | {t['cat'][cat]}: {why} |")
    lines += ["", t["shell"], "", t["shell_head"], "| --- | --- |"]
    for name, mapped in sorted(reg.SHELL_COMMANDS.items()):
        cell = (
            f"`coffer {mapped}`"
            if isinstance(mapped, str)
            else f"{t['cat'][mapped[0]]}: {mapped[1]}"
        )
        lines.append(f"| `{name}` | {cell} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    found, stats = _audit()
    for line in found:
        print(f"cli_coverage: {line}", file=sys.stderr)
    if "--write" in argv:
        for locale, path in PAGES.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render(locale), encoding="utf-8")
    elif "--check" in argv:
        for locale, path in PAGES.items():
            if not path.exists() or path.read_text(encoding="utf-8") != render(locale):
                print(
                    f"cli_coverage: {path.relative_to(REPO_ROOT)} is stale — run "
                    "`.venv/bin/python scripts/cli_coverage.py --write`",
                    file=sys.stderr,
                )
                found.append(str(path))
    print(summary(stats))
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
