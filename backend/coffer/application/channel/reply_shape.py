"""One structure pass over a finished reply, before the platform renderer.

Spec channels "Shape a reply for what the chat can show". An agent answers in
GitHub-flavoured markdown; a chat can show only part of it. What each transport
can show is a declared capability, never its type:

- ``renders_tables`` false (SeaTalk: a table arrives as raw pipes, and fails in
  a card) → each table becomes one bullet per row, ``- **checkout** · failed ·
  3DS timeout``; a table too big to read that way keeps its first five rows as
  bullets and goes out whole as an attached CSV.
- ``max_inline_code_lines`` > 0 (SeaTalk: 30) → a longer fenced block keeps its
  first three lines in the reply and goes out whole as an attached file.

And for every transport, :func:`split_details` finds the ``## Details`` section
the agent is asked to put long content under, so a transport can collapse it
(Telegram) or move it to a card (SeaTalk).

Pure: no I/O. The files it returns are text for the caller to stage and upload.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

__all__ = ["ReplyFile", "ShapedReply", "shape_reply", "split_details"]

#: A table small enough to read as bullets alone; past either bound the whole
#: table is attached as a CSV and only the first rows stay in the reply.
_TABLE_BULLET_ROWS = 12
_TABLE_BULLET_COLUMNS = 4
_TABLE_PREVIEW_ROWS = 5
#: What stays of an attached code block: enough to see what it is.
_CODE_PREVIEW_LINES = 3

_DETAILS_HEADING = re.compile(r"^#{1,3}[ \t]+details[ \t]*:?[ \t]*$", re.IGNORECASE | re.MULTILINE)
_FENCE_OPEN = re.compile(r"^([ \t]*)```([A-Za-z0-9_+-]*)[ \t]*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_CODE_SUFFIX = {
    "diff": ".diff",
    "patch": ".diff",
    "json": ".json",
    "csv": ".csv",
    "md": ".md",
    "log": ".log",
    "console": ".log",
}


@dataclass(frozen=True)
class ReplyFile:
    """A file the reply sends beside its text: a table's CSV, a long log."""

    filename: str
    content: str


@dataclass(frozen=True)
class ShapedReply:
    body: str
    files: tuple[ReplyFile, ...] = ()


def split_details(markdown: str) -> tuple[str, str]:
    """``(head, details)``: the reply before its ``## Details`` heading and the
    section under it (heading removed); ``details`` is "" when there is none."""
    match = _DETAILS_HEADING.search(markdown)
    if match is None:
        return markdown, ""
    return markdown[: match.start()].rstrip(), markdown[match.end() :].strip()


def _cells(line: str) -> list[str]:
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def _is_table_start(lines: list[str], i: int) -> bool:
    return (
        i + 1 < len(lines)
        and "|" in lines[i]
        and _TABLE_SEPARATOR.match(lines[i + 1]) is not None
        and "-" in lines[i + 1]
    )


def _bullet(cells: list[str]) -> str:
    cells = [c for c in cells if c] or ["—"]
    first, rest = cells[0], cells[1:]
    return " · ".join([f"- **{first}**", *rest]) if rest else f"- **{first}**"


def _csv(header: list[str], rows: list[list[str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


def shape_reply(
    markdown: str,
    *,
    renders_tables: bool = True,
    max_inline_code_lines: int = 0,
    attach: bool = True,
) -> ShapedReply:
    """Rewrite what the chat cannot show; return the new body and its files.

    ``attach`` false (the transport cannot send files) keeps everything in the
    body: every table row as a bullet, every code block inline."""
    if not attach:
        max_inline_code_lines = 0
    if renders_tables and max_inline_code_lines <= 0:
        return ShapedReply(markdown)
    lines = markdown.split("\n")
    out: list[str] = []
    files: list[ReplyFile] = []
    i = 0
    while i < len(lines):
        fence = _FENCE_OPEN.match(lines[i])
        if fence is not None:
            end = next(
                (j for j in range(i + 1, len(lines)) if lines[j].strip().startswith("```")),
                len(lines),
            )
            body = lines[i + 1 : end]
            if 0 < max_inline_code_lines < len(body):
                name = f"log-{len(files) + 1}{_CODE_SUFFIX.get(fence.group(2).lower(), '.txt')}"
                files.append(ReplyFile(name, "\n".join(body) + "\n"))
                out.extend([lines[i], *body[:_CODE_PREVIEW_LINES], "```"])
                out.append(f"*… {len(body)} lines in {name}*")
            else:
                out.extend(lines[i : end + 1])
            i = end + 1
            continue
        if not renders_tables and _is_table_start(lines, i):
            header = _cells(lines[i])
            j = i + 2
            rows: list[list[str]] = []
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                rows.append(_cells(lines[j]))
                j += 1
            big = attach and (len(rows) > _TABLE_BULLET_ROWS or len(header) > _TABLE_BULLET_COLUMNS)
            shown = rows[:_TABLE_PREVIEW_ROWS] if big else rows
            out.extend(_bullet(r) for r in shown)
            if big:
                name = f"table-{len(files) + 1}.csv"
                files.append(ReplyFile(name, _csv(header, rows)))
                out.append(f"*… {len(rows)} rows in {name}*")
            i = j
            continue
        out.append(lines[i])
        i += 1
    return ShapedReply("\n".join(out), tuple(files))
