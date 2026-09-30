"""A config file's change as unified-diff hunks, safe to show a person.

Spec agent-registry "Plan an import of agents' direct MCP entries": the import
preview shows, per agent config file, what removing the chosen entries changes.
The hunks are computed against the file's real text and what the entry remover
would write; every line shown — removed, added *and* context — is passed
through :func:`redact_line`, because a context line may carry another entry's
token. Only hunks travel, never the whole file (``~/.claude.json`` can be
megabytes). Pure: no I/O.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from coffer.domain.agent.mcp_entries import McpEntry, looks_secret

#: What a redacted value reads as.
REDACTED = "••••••"
#: Lines of unchanged text around each change.
CONTEXT_LINES = 3
#: A shown line longer than this is cut.
LINE_MAX = 400
#: A value this short is not replaced inside other text.
_MIN_LITERAL = 4

# ``"key": "value"`` (JSON) and ``key = "value"`` / ``key = 'value'`` (TOML,
# inline tables included): the key, the separator, and the quoted value.
_PAIR_RE = re.compile(
    r"""(?P<key>"(?:[^"\\]|\\.)*"|'[^']*'|[A-Za-z0-9_.\-]+)(?P<sep>\s*[:=]\s*)"""
    r"""(?P<q>["'])(?P<value>(?:(?!(?P=q))[^\\]|\\.)*)(?P=q)"""
)
_ARG_FLAG_RE = re.compile(r"^--?(?P<flag>[A-Za-z0-9_\-]+)(?:=(?P<value>.+))?$")


@dataclass(frozen=True)
class DiffLine:
    kind: Literal["context", "add", "remove"]
    old_line: int | None
    new_line: int | None
    text: str


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str | None
    lines: tuple[DiffLine, ...]

    @property
    def header(self) -> str:
        suffix = f" {self.section}" if self.section else ""
        return (
            f"@@ -{self.old_start},{self.old_count} +{self.new_start},{self.new_count} @@{suffix}"
        )


def entry_secret_literals(entries: Iterable[McpEntry]) -> list[str]:
    """Every value in ``entries`` that looks secret: env and header values under
    a secret-looking key, the value after a secret-looking flag in the args
    (``--token abc``, ``--api-key=abc``), and secret-looking extra keys."""
    out: list[str] = []
    for e in entries:
        for mapping in (e.env, e.headers):
            out.extend(v for k, v in mapping.items() if v and looks_secret(k))
        out.extend(str(v) for k, v in e.extra.items() if isinstance(v, str) and looks_secret(k))
        args = list(e.args)
        for i, arg in enumerate(args):
            m = _ARG_FLAG_RE.match(arg)
            if m is None or not looks_secret(m.group("flag").replace("-", "_")):
                continue
            if m.group("value"):
                out.append(m.group("value"))
            elif i + 1 < len(args):
                out.append(args[i + 1])
    return out


def _key_name(raw: str) -> str:
    return raw[1:-1] if raw[:1] in {'"', "'"} else raw


def redact_line(line: str, literals: Sequence[str]) -> str:
    """``line`` with every secret-looking key's value, and every known secret
    literal, replaced by :data:`REDACTED`; cut to :data:`LINE_MAX`."""

    def _pair(m: re.Match[str]) -> str:
        if not m.group("value") or not looks_secret(_key_name(m.group("key"))):
            return m.group(0)
        q = m.group("q")
        return f"{m.group('key')}{m.group('sep')}{q}{REDACTED}{q}"

    text = _PAIR_RE.sub(_pair, line)
    for value in sorted({v for v in literals if len(v) >= _MIN_LITERAL}, key=len, reverse=True):
        text = text.replace(value, REDACTED)
    return text[:LINE_MAX]


def diff_hunks(
    before: str,
    after: str,
    *,
    literals: Sequence[str] = (),
    section: str | None = None,
    context: int = CONTEXT_LINES,
) -> tuple[tuple[DiffHunk, ...], int, int]:
    """The hunks turning ``before`` into ``after``, redacted, and the added and
    removed line counts."""
    a = before.splitlines()
    b = after.splitlines()
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    hunks: list[DiffHunk] = []
    added = removed = 0
    for group in matcher.get_grouped_opcodes(context):
        lines: list[DiffLine] = []
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for k in range(i2 - i1):
                    lines.append(
                        DiffLine(
                            "context", i1 + k + 1, j1 + k + 1, redact_line(a[i1 + k], literals)
                        )
                    )
                continue
            for k in range(i1, i2):
                lines.append(DiffLine("remove", k + 1, None, redact_line(a[k], literals)))
                removed += 1
            for k in range(j1, j2):
                lines.append(DiffLine("add", None, k + 1, redact_line(b[k], literals)))
                added += 1
        first, last = group[0], group[-1]
        old_count = last[2] - first[1]
        new_count = last[4] - first[3]
        hunks.append(
            DiffHunk(
                old_start=first[1] + 1 if old_count else first[1],
                old_count=old_count,
                new_start=first[3] + 1 if new_count else first[3],
                new_count=new_count,
                section=section,
                lines=tuple(lines),
            )
        )
    return tuple(hunks), added, removed


#: The longest name a new MCP server may take (the MCP kind's registration cap).
SERVER_NAME_MAX = 24
_NAME_OUTSIDE = re.compile(r"[^a-z0-9_.-]+")
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")


def normalise_server_name(raw: str) -> str:
    """``raw`` as the daemon registers an MCP server name — the same rule the
    web UI's ``normaliseServerName`` applies: lower case, every run of other
    characters one ``-``, ``__`` collapsed, repeated and edge hyphens removed."""
    name = _NAME_OUTSIDE.sub("-", raw.lower())
    name = re.sub(r"_{2,}", "_", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name or "server"


def server_name_usable(name: str) -> bool:
    """Whether a new MCP server may be registered under ``name``."""
    return bool(_NAME_PATTERN.match(name)) and "__" not in name and len(name) <= SERVER_NAME_MAX


__all__ = [
    "CONTEXT_LINES",
    "REDACTED",
    "SERVER_NAME_MAX",
    "DiffHunk",
    "DiffLine",
    "diff_hunks",
    "entry_secret_literals",
    "normalise_server_name",
    "redact_line",
    "server_name_usable",
]
