# ruff: noqa: RUF001 — the Chinese page's own words use full-width punctuation.
"""Generate the docs site's CLI reference (and its Chinese twin) from the Typer app.

The reference is one index page, ``docs-site/reference/cli.md`` (the global
options and a table of every top-level command group), plus one page per
group under ``docs-site/reference/cli/`` with every command, argument and
option in that group. The pages are built by walking the real command tree
(``typer.main.get_command``) through click's introspection API, so everything
on them is something the CLI actually has. Output is deterministic: the same
code produces the same bytes, which is what lets
``scripts/check_cli_reference.py`` fail CI when a page drifts, and a group
page left behind by a removed group counts as drift too.

The Chinese pages, under ``docs-site/zh/reference/``, are the same walk with
the pages' own prose, headings and table labels in Chinese. Help text comes
from the CLI, which speaks English, so it stays English on both.

    .venv/bin/python docs-site/scripts/gen_cli_reference.py          # write the page
    .venv/bin/python docs-site/scripts/gen_cli_reference.py --stdout # print it
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE = REPO_ROOT / "docs-site"
#: Where each locale's index page and per-group pages go, and the URL prefix
#: its links use.
LOCALE_ROOTS: dict[str, tuple[Path, str]] = {
    "en": (SITE / "reference", ""),
    "zh": (SITE / "zh" / "reference", "/zh"),
}
#: The directories whose pages this generator owns outright: a page in one of
#: them that the CLI no longer produces is stale.
OWNED_DIRS: tuple[Path, ...] = tuple(root / "cli" for root, _ in LOCALE_ROOTS.values())

sys.path.insert(0, str(REPO_ROOT / "backend"))

HEADER = """\
---
title: CLI reference
description: Every coffer command, argument and option, generated from the CLI itself.
---

# CLI reference

This page lists the options every `coffer` command takes and each top-level command
group. Each group has its own page with every command, argument and option in it. The
pages are generated from the CLI's own command tree, so they match what
`coffer <command> --help` prints for the version on `main`.

::: info Generated pages
Do not edit these pages by hand. Regenerate them with `make docs-reference`
(which runs `docs-site/scripts/gen_cli_reference.py`); `make lint` fails when a
page and the CLI disagree.
:::

Most commands talk to the local daemon over its management API and start it if it is
not running. For the exit codes every command shares, see
[Error codes](/reference/error-codes#cli-exit-codes).
"""

HEADER_ZH = """\
---
title: CLI 参考
description: 每一个 coffer 命令、参数和选项，由 CLI 自身生成。
---

# CLI 参考 {#cli-reference}

本页列出每个 `coffer` 命令都接受的选项，以及每个顶层命令组。每个命令组有自己的页面，
列出组内的每个命令、参数和选项。这些页面由 CLI 自己的命令树生成，所以和 `main` 上的
版本执行 `coffer <command> --help` 打印的内容一致。命令说明直接取自 CLI，因此保持英文。

::: info 生成的页面
不要手工编辑这些页面。用 `make docs-reference` 重新生成（它会运行
`docs-site/scripts/gen_cli_reference.py`）；页面和 CLI 不一致时 `make lint` 会失败。
:::

大多数命令通过管理 API 与本机的守护进程通信，守护进程没在运行时会先把它启动。所有命令
共用的退出码见[错误码](/zh/reference/error-codes#cli-exit-codes)。
"""

#: The page's own words, per locale. Everything else on the page comes from the CLI.
LABELS: dict[str, dict[str, str]] = {
    "en": {
        "header": HEADER,
        "global": "## Global options",
        "groups": "## Command groups",
        "groups_table": "| Group | Description |",
        "params_table": "| Name | Type | Default | Description |",
        "commands": "## Commands",
        "commands_table": "| Command | What it does |",
        "synopsis": "Synopsis",
        "args": "Arguments and options",
        "argument": "argument",
        "option": "option",
        "flag": "flag",
        "required": "required",
        "repeatable": " (repeatable)",
        "variadic": " (variadic)",
        "deprecated": "::: warning Deprecated\nThis command is deprecated.\n:::",
        "subcommands": "Subcommands: {names}.",
        "group_note": (
            "This page matches what `coffer {name} --help` prints. Add `--help` to any "
            "command below to see its options in the terminal."
        ),
    },
    "zh": {
        "header": HEADER_ZH,
        "global": "## 全局选项 {#global-options}",
        "groups": "## 命令组 {#command-groups}",
        "groups_table": "| 命令组 | 说明 |",
        "params_table": "| 名称 | 类型 | 默认值 | 说明 |",
        "commands": "## 命令 {#commands}",
        "commands_table": "| 命令 | 说明 |",
        "synopsis": "概要",
        "args": "参数与选项",
        "argument": "参数",
        "option": "选项",
        "flag": "开关",
        "required": "必填",
        "repeatable": "（可重复）",
        "variadic": "（可变个数）",
        "deprecated": "::: warning 已弃用\n这个命令已弃用。\n:::",
        "subcommands": "子命令：{names}。",
        "group_note": (
            "本页与 `coffer {name} --help` 打印的内容一致。在下面任何命令后加 `--help`，"
            "即可在终端里查看它的选项。"
        ),
    },
}

_CODE_SPAN = re.compile(r"(``.+?``|`[^`]+`)")


def _escape_prose(text: str) -> str:
    """Make help text safe for VitePress: Markdown outside code spans cannot
    open HTML tags, Vue interpolations or emphasis by accident."""
    out: list[str] = []
    for i, part in enumerate(_CODE_SPAN.split(text)):
        if i % 2 == 1:
            out.append(part)
            continue
        part = part.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        part = part.replace("*", "\\*")
        # `{{` is a Vue interpolation even after entity decoding; code spans
        # are the only safe carrier.
        part = re.sub(r"(\{\{+|\}\}+)", r"`\1`", part)
        out.append(part)
    return "".join(out)


def _paragraphs(text: str) -> list[str]:
    """Split help text into Markdown paragraphs, joining wrapped lines."""
    text = text.split("\f", 1)[0]
    paras: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip() and ln.strip() != "\b"]
        if not lines:
            continue
        listy = any(re.match(r"\s*([-*•]|\d+[.)])\s", ln) for ln in lines)
        if listy:
            items: list[str] = []
            for ln in lines:
                stripped = ln.strip()
                if re.match(r"([-*•]|\d+[.)])\s", stripped) or not items:
                    items.append(re.sub(r"^[*•]\s", "- ", stripped))
                else:
                    items[-1] += " " + stripped
            paras.append(
                "\n".join(
                    _escape_prose(it) if not it.startswith("- ") else "- " + _escape_prose(it[2:])
                    for it in items
                )
            )
        else:
            paras.append(_escape_prose(" ".join(ln.strip() for ln in lines)))
    return paras


def _cell(text: str) -> str:
    """One table cell: a single line with pipes escaped."""
    flat = " ".join(" ".join(_paragraphs(text)).split())
    return flat.replace("|", "\\|") if flat else ""


def _is_unset(value: Any) -> bool:
    return value is None or "UNSET" in repr(value) or "Sentinel" in type(value).__name__


def _param_name(prm: Any) -> str:
    if prm.param_type_name == "argument":
        return f"`{(prm.metavar or prm.name).upper()}`"
    names = sorted(prm.opts, key=lambda o: (not o.startswith("--"), o))
    label = ", ".join(names)
    if prm.secondary_opts:
        label += " / " + ", ".join(prm.secondary_opts)
    return f"`{label}`"


def _param_type(prm: Any, lab: dict[str, str]) -> str:
    if getattr(prm, "is_flag", False) and not prm.secondary_opts:
        return lab["flag"]
    ptype = prm.type
    choices = getattr(ptype, "choices", None)
    if choices:
        return " \\| ".join(f"`{c}`" for c in choices)
    name = getattr(ptype, "name", "") or type(ptype).__name__
    name = name.lower()
    lo, hi = getattr(ptype, "min", None), getattr(ptype, "max", None)
    if lo is not None or hi is not None:
        name = (
            name.replace(" range", "") + f" ({'' if lo is None else lo}-{'' if hi is None else hi})"
        )
    if getattr(prm, "multiple", False) or (prm.nargs not in (1, 0) and prm.nargs is not None):
        name += lab["repeatable"] if prm.param_type_name == "option" else lab["variadic"]
    return name


def _param_default(prm: Any, lab: dict[str, str]) -> str:
    if prm.required:
        return lab["required"]
    default = prm.default
    if callable(default) or _is_unset(default):
        return ""
    if isinstance(default, bool):
        if getattr(prm, "is_flag", False) and not prm.secondary_opts and default is False:
            return ""
        return f"`{str(default).lower()}`"
    if isinstance(default, (list, tuple)):
        return "" if not default else f"`{', '.join(map(str, default))}`"
    text = str(default)
    return f"`{text}`" if text else '`""`'


def _usage(chain: list[tuple[str, Any]]) -> str:
    """The usage line click prints, for a command reached through ``chain``."""
    ctx = None
    for name, cmd in chain:
        ctx = cmd.context_class(cmd, info_name=name, parent=ctx)
    assert ctx is not None
    pieces = chain[-1][1].collect_usage_pieces(ctx)
    return " ".join([name for name, _ in chain] + pieces)


def _visible_params(cmd: Any) -> list[Any]:
    return [p for p in cmd.params if not getattr(p, "hidden", False)]


def _params_table(cmd: Any, lab: dict[str, str]) -> list[str]:
    params = _visible_params(cmd)
    if not params:
        return []
    rows = [lab["params_table"], "| --- | --- | --- | --- |"]
    for prm in params:
        kind = lab["argument"] if prm.param_type_name == "argument" else lab["option"]
        help_text = getattr(prm, "help", None) or ""
        cells = (
            f'{_param_name(prm)} <span class="cli-chip">{kind}</span>',
            _param_type(prm, lab),
            _param_default(prm, lab),
            _cell(help_text),
        )
        rows.append("| " + " | ".join(cells) + " |")
    return [*rows, ""]


def _children(group: Any) -> list[tuple[str, Any]]:
    return [(n, c) for n, c in group.commands.items() if not getattr(c, "hidden", False)]


Chain = list[tuple[str, Any]]


def _label(text: str) -> list[str]:
    return [f'<p class="cli-label">{text}</p>', ""]


def _anchor(title: str) -> str:
    """The id VitePress gives a ``##`` heading with this text."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _command_titles(chain: Chain) -> list[tuple[str, str]]:
    """(heading, first sentence) for every command under a group, in page order."""
    out: list[tuple[str, str]] = []
    for name, child in _children(chain[-1][1]):
        child_chain = [*chain, (name, child)]
        title = " ".join(n for n, _ in child_chain[1:])
        out.append((title, _first_sentence(child.help or child.short_help or "")))
        if hasattr(child, "commands"):
            out += _command_titles(child_chain)
    return out


def _command_block(chain: Chain, lab: dict[str, str]) -> list[str]:
    cmd = chain[-1][1]
    lines = [f"## {' '.join(name for name, _ in chain[1:])}", ""]
    if getattr(cmd, "deprecated", False):
        lines += [lab["deprecated"], ""]
    for para in _paragraphs(cmd.help or cmd.short_help or ""):
        lines += [para, ""]
    lines += _label(lab["synopsis"])
    lines += ["```sh", _usage(chain), "```", ""]
    table = _params_table(cmd, lab)
    if table:
        lines += _label(lab["args"]) + table
    if hasattr(cmd, "commands"):
        subs = _children(cmd)
        if subs:
            names = ", ".join(f"`{n}`" for n, _ in subs)
            lines += [lab["subcommands"].format(names=names), ""]
    return lines


def _walk_group(chain: Chain, lab: dict[str, str]) -> list[str]:
    """Every command under a group, depth first, in declaration order."""
    out: list[str] = []
    for name, child in _children(chain[-1][1]):
        child_chain = [*chain, (name, child)]
        out += _command_block(child_chain, lab)
        if hasattr(child, "commands"):
            out += _walk_group(child_chain, lab)
    return out


def _first_sentence(text: str) -> str:
    paras = _paragraphs(text)
    if not paras:
        return ""
    head = re.split(r"(?<=[.!?])\s", paras[0], maxsplit=1)[0]
    return head.replace("|", "\\|")


def _plain_first_sentence(text: str) -> str:
    """The first sentence of help text, unescaped, for a page's description."""
    text = text.split("\f", 1)[0].strip()
    first = re.split(r"\n\s*\n", text, maxsplit=1)[0] if text else ""
    flat = " ".join(first.split())
    return re.split(r"(?<=[.!?])\s", flat, maxsplit=1)[0]


def _root() -> Any:
    import typer

    from coffer.surfaces.cli.main import app

    return typer.main.get_command(app)


def _finish(lines: list[str]) -> str:
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip("\n") + "\n"


def render(lang: str = "en") -> str:
    """The index page: global options and a table of every command group."""
    root = _root()
    root_chain: Chain = [("coffer", root)]
    lab = LABELS[lang]
    prefix = LOCALE_ROOTS[lang][1]
    lines = [lab["header"]]
    lines += [lab["global"], ""]
    lines += ["```sh", _usage(root_chain), "```", ""]
    lines += _params_table(root, lab)
    lines += [lab["groups"], ""]
    lines += [lab["groups_table"], "| --- | --- |"]
    for name, group in _children(root):
        summary = _first_sentence(group.help or group.short_help or "")
        lines.append(f"| [`coffer {name}`]({prefix}/reference/cli/{name}) | {summary} |")
    lines.append("")
    return _finish(lines)


def render_group(lang: str, name: str, group: Any) -> str:
    """One group's page: the group itself, then every command under it."""
    root_chain: Chain = [("coffer", _root())]
    lab = LABELS[lang]
    chain = [*root_chain, (name, group)]
    description = _plain_first_sentence(group.help or group.short_help or "")
    lines = [
        "---",
        f"title: coffer {name}",
        f"description: {json.dumps(description, ensure_ascii=False)}",
        "pageClass: cli-ref",
        "---",
        "",
        f"# coffer {name}",
        "",
    ]
    paras = _paragraphs(group.help or "")
    if paras:
        lines += [paras[0], ""]
    lines += ["```sh", _usage(chain), "```", ""]
    lines += [lab["group_note"].format(name=name), ""]
    for para in paras[1:]:
        lines += [para, ""]
    lines += _params_table(group, lab)
    if hasattr(group, "commands"):
        titles = _command_titles(chain)
        if titles:
            lines += [lab["commands"], "", lab["commands_table"], "| --- | --- |"]
            for title, summary in titles:
                lines.append(f"| [`{title}`](#{_anchor(title)}) | {summary} |")
            lines.append("")
        lines += _walk_group(chain, lab)
    return _finish(lines)


def render_all() -> dict[Path, str]:
    """Every page this generator owns, keyed by where it is written."""
    root = _root()
    pages: dict[Path, str] = {}
    for lang, (base, _) in LOCALE_ROOTS.items():
        pages[base / "cli.md"] = render(lang)
        for name, group in _children(root):
            pages[base / "cli" / f"{name}.md"] = render_group(lang, name, group)
    return pages


def stale_pages(pages: dict[Path, str]) -> list[Path]:
    """Pages in an owned directory that the CLI no longer produces."""
    return sorted(
        path
        for directory in OWNED_DIRS
        if directory.is_dir()
        for path in directory.glob("*.md")
        if path not in pages
    )


def main(argv: list[str]) -> int:
    if "--stdout" in argv:
        sys.stdout.write(render())
        return 0
    pages = render_all()
    for path in stale_pages(pages):
        path.unlink()
        print(f"removed {path.relative_to(REPO_ROOT)}")
    for path, text in pages.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"wrote {len(pages)} pages under docs-site/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
