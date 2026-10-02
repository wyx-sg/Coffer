"""Read what a tool's ``--help`` printed into a :class:`HelpNode`.

One section-based reader serves the help formats in common use: click and
typer (plain and rich boxes), argparse (including ``{a,b}`` subparsers),
cobra (Go), clap (Rust), commander (Node) and the ``gh`` / ``git`` style of
capitalised or sentence headings. A section is a heading at the left margin
(``Options:``, ``positional arguments:``, ``CORE COMMANDS``, a rich box title)
followed by indented entries; what a heading means is decided by its words
(command, option, flag, argument). Anything else — an example block, help
topics, free text — is left to the raw text, which is always kept.

Pure: text in, node out. The text is untrusted tool output, so nothing here
evaluates it, and every pattern is anchored and linear.
"""

from __future__ import annotations

import re

from coffer.domain.skill.cli_help import (
    HelpArgument,
    HelpNode,
    HelpOption,
    HelpSubcommand,
)

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_BOX_TOP = re.compile(r"^\s*[╭┌┏]─*\s*(.*?)\s*─*[╮┐┓]\s*$")
_BOX_BOTTOM = re.compile(r"^\s*[╰└┗]─*[╯┘┛]\s*$")
_BOX_ROW = re.compile(r"^\s*[│┃](.*?)[│┃]?\s*$")
_USAGE_INLINE = re.compile(r"^(?i:usage):\s*(\S.*)$")
_HEADER = re.compile(r"^(?P<h>[A-Za-z][^:]{0,80}):\s*$")
_UPPER_HEADER = re.compile(r"^[A-Z][A-Z0-9 /&-]{2,40}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_GAP = re.compile(r"\s{2,}")
_DEFAULT = re.compile(r"\[default:\s*([^\]]*)\]|\(default:?\s+([^)]*)\)")
_REQUIRED = re.compile(r"\[required\]|\(required\)")
_SET = re.compile(r"^\{([^{}\s]+)\}$")
#: A value placeholder that follows a flag: ``<FILE>``, ``FILE``, ``{a,b}``,
#: ``[a|b]``, or a Go type word cobra prints.
_METAVAR = re.compile(
    r"^(<[^>\s]+>|[A-Z][A-Z0-9_]*(\.\.\.)?|\{[^}\s]+\}|\[[A-Z][A-Z0-9_|.-]*\]|\[[^\]\s]*\|[^\]\s]*\])$"
)
_GO_TYPES = frozenset(
    [
        "string",
        "strings",
        "int",
        "ints",
        "int8",
        "int16",
        "int32",
        "int64",
        "uint",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "float",
        "float32",
        "float64",
        "duration",
        "stringArray",
        "stringSlice",
        "stringToString",
        "intSlice",
        "bytesHex",
        "bytesBase64",
        "ip",
    ]
)
_DESCRIPTION_MAX = 1500


def parse_help(raw: str, path: tuple[str, ...], *, truncated: bool = False) -> HelpNode:
    """The node ``raw`` describes; ``structured`` says whether anything in it
    was recognised."""
    lines = _normalise(raw)
    usage, preamble, sections = _split(lines)
    subcommands: list[HelpSubcommand] = []
    options: list[HelpOption] = []
    arguments: list[HelpArgument] = []
    for kind, body in sections:
        if kind == "commands":
            _add(subcommands, _commands(body), lambda s: s.name)
        elif kind == "options":
            _add(options, _options(body), lambda o: o.names)
        elif kind == "arguments":
            args, subs = _arguments(body)
            _add(arguments, args, lambda a: a.name)
            _add(subcommands, subs, lambda s: s.name)
    description = _paragraphs(preamble)
    return HelpNode(
        path=path,
        usage=usage,
        description=description,
        subcommands=tuple(subcommands),
        options=tuple(options),
        arguments=tuple(arguments),
        raw=raw,
        structured=bool(usage or subcommands or options or arguments),
        truncated=truncated,
    )


def _add(into: list, found: list, key) -> None:  # type: ignore[type-arg,no-untyped-def]
    seen = {key(item) for item in into}
    for item in found:
        if key(item) not in seen:
            seen.add(key(item))
            into.append(item)


def _normalise(raw: str) -> list[str]:
    """Plain lines: colours stripped, tabs expanded, rich boxes turned into a
    titled section of indented rows."""
    out: list[str] = []
    plain = _ANSI.sub("", raw).replace("\r", "").expandtabs(4).split("\n")
    margin = min(
        (
            _indent(line)
            for line in plain
            if line.strip() and not any(b.match(line) for b in (_BOX_TOP, _BOX_ROW, _BOX_BOTTOM))
        ),
        default=0,
    )
    for line in plain:
        top = _BOX_TOP.match(line)
        if top is not None:
            out.append(f"{top.group(1) or 'Panel'}:")
        elif _BOX_BOTTOM.match(line):
            out.append("")
        else:
            row = _BOX_ROW.match(line)
            out.append(row.group(1).rstrip() if row else line[margin:].rstrip())
    return out


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _kind(title: str) -> str:
    t = title.lower()
    if t.startswith("usage"):
        return "usage"
    if any(w in t for w in ("topic", "example", "learn", "environment")):
        return "other"
    if "option" in t or "flag" in t:
        return "options"
    if "command" in t:
        return "commands"
    if "argument" in t or t in ("args", "positional"):
        return "arguments"
    return "other"


def _header(line: str) -> str | None:
    if not line or line[0] == " ":
        return None
    match = _HEADER.match(line)
    if match is not None:
        return match.group("h")
    return line if _UPPER_HEADER.match(line) else None


def _split(lines: list[str]) -> tuple[str | None, list[str], list[tuple[str, list[str]]]]:
    usage: list[str] = []
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    mode = ""
    for line in lines:
        inline = _USAGE_INLINE.match(line)
        title = None if inline else _header(line)
        if inline or (title is not None and _kind(title) == "usage"):
            usage, mode = [inline.group(1).strip()] if inline else [], "usage"
        elif title is not None:
            sections.append((_kind(title), []))
            mode = "section"
        elif mode == "usage" and line.strip() and _indent(line) > 0:
            usage.append(line.strip())
        elif mode == "usage" and not line.strip() and not usage:
            continue
        else:
            if mode == "usage":
                mode = ""
            if mode == "section":
                sections[-1][1].append(line)
            elif not sections and line.strip() and not line.lstrip().startswith("-"):
                preamble.append(line.strip())
    return ("\n".join(usage) or None), preamble, sections


def _paragraphs(lines: list[str]) -> str | None:
    text = " ".join(lines).strip()
    return text[:_DESCRIPTION_MAX] if text else None


def _entries(body: list[str], *, flags: bool = False) -> list[list[str]]:
    """The entries of a section, each as its first line then its continuation
    lines (all stripped). An entry starts at the section's own indent (a flag
    starts one wherever it is, since cobra indents a long-only flag deeper); a
    line at the left margin is a group title or an epilogue and ends the entry."""
    indented = [_indent(line) for line in body if line.strip() and _indent(line) > 0]
    if not indented:
        return []
    base = min(indented)
    entries: list[list[str]] = []
    for line in body:
        if not line.strip():
            continue
        depth = _indent(line)
        if depth == 0:
            entries.append([])
        elif depth == base or (flags and line.strip().startswith(("-", "*"))):
            entries.append([line.strip()])
        elif entries and entries[-1]:
            entries[-1].append(line.strip())
    return [e for e in entries if e]


def _named(text: str) -> tuple[str, str | None] | None:
    """``name  summary`` of one row: the first word (``pr:`` and ``add,`` lose
    their punctuation) and what follows the first wide gap."""
    parts = _GAP.split(text.strip(), maxsplit=1)
    words = parts[0].split()
    name = words[0].rstrip(":,") if words else ""
    if not _NAME.match(name):
        return None
    return name, (" ".join(parts[1].split()) if len(parts) > 1 else None)


def _commands(body: list[str]) -> list[HelpSubcommand]:
    out: list[HelpSubcommand] = []
    for entry in _entries(body):
        found = _named(" ".join(entry))
        if found is not None:
            out.append(HelpSubcommand(*found))
    return out


def _arguments(body: list[str]) -> tuple[list[HelpArgument], list[HelpSubcommand]]:
    """Positional arguments, and the subcommands argparse lists among them
    (``{a,b}`` followed by one indented row per subcommand)."""
    args: list[HelpArgument] = []
    subs: list[HelpSubcommand] = []
    for entry in _entries(body):
        parts = _GAP.split(entry[0], maxsplit=1)
        token = parts[0]
        if _SET.match(token):
            subs.extend(_commands(["    " + row for row in entry[1:]]))
            continue
        name = token.strip("<>[]*.,")
        if not _NAME.match(name):
            continue
        text = " ".join(parts[1:] + entry[1:])
        bracketed = token.startswith("[")
        required = (
            _REQUIRED.search(text) is not None or token.startswith(("<", "*")) or not bracketed
        )
        args.append(
            HelpArgument(name, " ".join(_clean_description(text).split()) or None, required)
        )
    return args, subs


def _is_metavar(token: str) -> bool:
    return bool(_METAVAR.match(token)) or token in _GO_TYPES


def _clean_description(text: str) -> str:
    return _REQUIRED.sub("", _DEFAULT.sub("", text)).strip()


def _options(body: list[str]) -> list[HelpOption]:
    out: list[HelpOption] = []
    for entry in _entries(body, flags=True):
        option = _option(" ".join(entry))
        if option is not None:
            out.append(option)
    return out


def _option(entry: str) -> HelpOption | None:
    required_star = entry.startswith("*")
    tokens = entry.lstrip("* ").split()
    names: list[str] = []
    metavar: str | None = None
    i = 0
    while i < len(tokens):
        bare = tokens[i].rstrip(",")
        if bare.startswith("-") and len(bare) > 1:
            for part in bare.split("/"):
                if part.startswith("-"):
                    name, _, value = part.partition("=")
                    names.append(name)
                    if value and metavar is None:
                        metavar = value.strip("<>[]") or None
        elif bare == "/" or (metavar is not None and bare == metavar):
            pass  # click's ``--a / --b`` separator; argparse repeats the metavar
        elif names and metavar is None and _is_metavar(bare):
            metavar = bare.strip("<>") if bare.startswith("<") else bare
        else:
            break
        i += 1
    if not names:
        return None
    text = " ".join(tokens[i:])
    found = _DEFAULT.search(text)
    default = next((g for g in (found.groups() if found else ()) if g is not None), None)
    required = required_star or _REQUIRED.search(text) is not None
    return HelpOption(
        names=tuple(names),
        metavar=metavar,
        description=" ".join(_clean_description(text).split()) or None,
        default=default.strip().strip("\"'") if default is not None and default.strip() else None,
        required=required,
    )


__all__ = ["parse_help"]
