#!/usr/bin/env python3
"""The error-code reference lists every code the management API maps, at its status.

``docs-site/reference/error-codes.md`` and its Chinese twin are written by hand:
each code carries a meaning and a usual fix, which no table in the code holds.
What the code does hold is the status table (``surfaces/http/errors._STATUS``,
with the maps it spreads in, and ``_HTTP_CODE`` for the synthetic codes the
HTTP layer names), so this gate holds the pages to it:

- every mapped code has a row in a ``| Code | HTTP | …`` table of each page;
- the row's HTTP column is the status the daemon sends it with;
- no such table lists a code the daemon does not map (a removed code, a typo).

Rows of the other tables on the page — startup errors, chat turn errors, MCP
gateway errors, exit codes — are not API error codes and are not compared.
``HTTP_<status>`` stands for every bare status without a named code.

Run with ``PYTHONPATH=backend`` (``make lint`` does). Exits non-zero with one
line per difference.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGES = (
    Path("docs-site/reference/error-codes.md"),
    Path("docs-site/zh/reference/error-codes.md"),
)
#: A table whose header row names the code, then the HTTP status.
_HEADER = re.compile(r"^\|\s*(?:Code|代码|错误码)\s*\|\s*HTTP\s*\|")
_ROW = re.compile(r"^\|\s*`(?P<code>[A-Z][A-Z0-9_<>a-z]*)`\s*\|\s*(?P<http>[^|]*?)\s*\|")
#: The row that stands for every bare status without a named code.
_BARE = "HTTP_<status>"


def mapped_codes() -> dict[str, int]:
    """Every code the daemon maps, with the status it is sent with."""
    from coffer.surfaces.http import errors

    codes = dict(errors._STATUS)
    for status, code in errors._HTTP_CODE.items():
        codes.setdefault(code, status)
    return codes


def listed_codes(text: str) -> dict[str, list[tuple[int, str]]]:
    """code -> [(line, HTTP cell)] for every row of the page's ``Code | HTTP`` tables."""
    listed: dict[str, list[tuple[int, str]]] = {}
    in_table = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _HEADER.match(line):
            in_table = True
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        if in_table and (row := _ROW.match(line)):
            listed.setdefault(row.group("code"), []).append((lineno, row.group("http")))
    return listed


def check_page(rel: str, text: str, codes: dict[str, int]) -> list[str]:
    problems: list[str] = []
    listed = listed_codes(text)
    for code, status in sorted(codes.items()):
        rows = listed.get(code)
        if not rows:
            problems.append(f"{rel}: no row for `{code}` (HTTP {status})")
            continue
        for lineno, http in rows:
            if http != str(status):
                problems.append(
                    f"{rel}:{lineno}: `{code}` says HTTP {http!r}; the daemon sends {status}"
                )
        if len(rows) > 1:
            problems.append(f"{rel}: `{code}` is listed {len(rows)} times")
    for code, rows in sorted(listed.items()):
        if code not in codes and code != _BARE:
            problems.append(f"{rel}:{rows[0][0]}: `{code}` is not a code the daemon maps")
    return problems


def main() -> int:
    codes = mapped_codes()
    problems: list[str] = []
    for page in PAGES:
        text = (REPO_ROOT / page).read_text(encoding="utf-8")
        problems += check_page(page.as_posix(), text, codes)
    for problem in problems:
        print(f"check_error_codes_reference: {problem}", file=sys.stderr)
    if problems:
        print(
            f"check_error_codes_reference: {len(problems)} difference(s) between the "
            "error-code pages and surfaces/http/errors.py",
            file=sys.stderr,
        )
        return 1
    print(f"check_error_codes_reference: {len(codes)} codes listed at their status in both pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
