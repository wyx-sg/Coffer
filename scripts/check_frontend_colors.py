#!/usr/bin/env python3
"""Keep colour literals out of the frontend, outside ``frontend/src/index.css``.

Every colour in the web UI is a theme token: ``src/index.css`` defines each
role once per theme (light and dark) and components ask for the role
(``bg-surface-raised``, ``text-danger``). A literal anywhere else is a colour
that does not follow the theme, so this script scans every ``.ts``, ``.tsx``
and ``.css`` file under ``frontend/src/`` except ``index.css`` and the
generated API types, and fails on:

* a hex colour (``#4353d8``, ``#fff``) — in a string, a style or an arbitrary
  Tailwind value such as ``bg-[#fff]``;
* a colour function (``rgb(``, ``rgba(``, ``hsl(``, ``hsla(``) that is not
  ``rgb(var(--token) …)`` — the one form that reads a token's channels;
* a Tailwind palette class (``bg-red-500``, ``text-emerald-600``,
  ``border-white``, ``text-black``), which bypasses the tokens the same way.

Comments are stripped first, so an issue reference such as ``#227`` in a
comment never trips it. SVG files are not scanned: a brand mark is shipped as
supplied. Stdlib-only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "frontend" / "src"
#: The one file allowed to hold colour literals: the token definitions.
ALLOWED = {SRC / "index.css"}
#: Generated wire types — nothing in them is styling.
SKIPPED_DIRS = (SRC / "lib" / "api" / "generated",)
SUFFIXES = {".ts", ".tsx", ".css"}

_PALETTE = (
    "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|"
    "blue|indigo|violet|purple|fuchsia|pink|rose"
)
_UTILITIES = (
    "bg|text|border|border-[trblxy]|ring|ring-offset|fill|stroke|from|via|to|outline|divide|"
    "decoration|shadow|accent|caret|placeholder"
)

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "hex colour",
        re.compile(r"(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])"),
    ),
    ("colour function", re.compile(r"(?<![A-Za-z0-9-])(?:rgba?|hsla?)\((?!\s*var\(--)")),
    ("colour function", re.compile(r"(?<![A-Za-z0-9-])hsla?\(\s*var\(--")),
    (
        "Tailwind palette class",
        re.compile(
            rf"(?<![\w-])(?:[\w-]+:)*(?:{_UTILITIES})-(?:(?:{_PALETTE})-\d{{2,3}}|white|black)"
            r"(?![\w-])"
        ),
    ),
)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
# A line comment starts at `//` that is not part of a URL (`https://`).
_LINE_COMMENT = re.compile(r"(?<![:\w])//[^\n]*")


def strip_comments(source: str) -> str:
    """Blank out comments, keeping line numbers stable."""

    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return _LINE_COMMENT.sub(blank, _BLOCK_COMMENT.sub(blank, source))


def scan_source(source: str) -> list[tuple[int, str, str]]:
    """``(line, rule, literal)`` for every colour literal in ``source``."""
    text = strip_comments(source)
    hits: list[tuple[int, str, str]] = []
    for label, pattern in RULES:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            hits.append((line, label, match.group(0)))
    return sorted(set(hits))


def _scanned(path: Path) -> bool:
    if path.suffix not in SUFFIXES or path in ALLOWED:
        return False
    return not any(path.is_relative_to(d) for d in SKIPPED_DIRS)


def scan_tree(root: Path = SRC) -> list[tuple[Path, int, str, str]]:
    found: list[tuple[Path, int, str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _scanned(path):
            continue
        for line, label, literal in scan_source(path.read_text(encoding="utf-8")):
            found.append((path, line, label, literal))
    return found


def main() -> int:
    found = scan_tree()
    if not found:
        print("check_frontend_colors: OK — no colour literals outside frontend/src/index.css.")
        return 0
    print(
        "check_frontend_colors: FAIL — colour literals outside the theme tokens:", file=sys.stderr
    )
    for path, line, label, literal in found:
        print(f"  {path.relative_to(REPO_ROOT)}:{line}: {label} `{literal}`", file=sys.stderr)
    print(
        "\n  Use a token role instead (bg-surface-raised, text-text-muted, text-danger …),\n"
        "  or add a role to frontend/src/index.css for both themes.\n"
        "  See .agents/visual-language.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
