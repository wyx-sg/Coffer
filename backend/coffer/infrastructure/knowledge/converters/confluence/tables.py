"""Tables: a Markdown table when every cell is plain, else a sanitised HTML table.

A table with merged cells (``colspan``/``rowspan`` over 1) or block content in
a cell (lists, code, nested tables, headings, panels …) cannot be a Markdown
table. It becomes an HTML table built only from ``table tr th td`` with
``colspan``/``rowspan``; each cell's content is Markdown set off by blank
lines, which a Markdown reader renders in place (so a code macro in a cell
keeps its fence and language, and the cell keeps its text).
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from bs4 import Tag

from coffer.infrastructure.knowledge.converters.confluence import macros
from coffer.infrastructure.knowledge.converters.confluence.text import SPACE

if TYPE_CHECKING:
    from coffer.infrastructure.knowledge.converters.confluence.storage import Walker

_BLOCK_IN_CELL = ("ul", "ol", "pre", "table", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6")


def _rows(table: Tag) -> list[Tag]:
    rows: list[Tag] = []
    for child in table.children:
        if not isinstance(child, Tag):
            continue
        if child.name == "tr":
            rows.append(child)
        elif child.name in ("thead", "tbody", "tfoot"):
            rows.extend(r for r in child.find_all("tr", recursive=False))
    return rows


def _cells(row: Tag) -> list[Tag]:
    return list(row.find_all(["th", "td"], recursive=False))


def _span(cell: Tag, name: str) -> int:
    try:
        return int(str(cell.get(name) or "1"))
    except ValueError:
        return 1


def _has_block(cell: Tag) -> bool:
    if cell.find(_BLOCK_IN_CELL) is not None or cell.find("ac:task-list") is not None:
        return True
    for macro in cell.find_all(list(macros.MACRO_TAGS)):
        name = macros.macro_name(macro)
        if name not in macros.INLINE and name not in macros.NAVIGATION:
            return True
    return False


def _plain_text(cell: Tag) -> str | None:
    """A cell holding only text (in at most one paragraph) as escaped HTML text."""
    tags = cell.find_all(True)
    if any(t.name not in ("p", "span") for t in tags) or sum(t.name == "p" for t in tags) > 1:
        return None
    return html.escape(SPACE.sub(" ", cell.get_text()).strip(), quote=False)


def render(walker: Walker, table: Tag) -> list[str]:
    rows = [cells for cells in (_cells(r) for r in _rows(table)) if cells]
    if not rows:
        return []
    merged = any(_span(c, "colspan") > 1 or _span(c, "rowspan") > 1 for r in rows for c in r)
    if merged or any(_has_block(c) for r in rows for c in r):
        return [_html(walker, rows)]
    return [_markdown(walker, rows)]


def _cell_markdown(walker: Walker, cell: Tag) -> str:
    paragraphs = walker.blocks(cell)
    text = "<br><br>".join(p.replace("\\\n", "<br>") for p in paragraphs)
    return text.replace("\n", " ").replace("|", "\\|").strip()


def _markdown(walker: Walker, rows: list[list[Tag]]) -> str:
    texts = [[_cell_markdown(walker, c) for c in row] for row in rows]
    width = max(len(r) for r in texts)
    for number, (row, cells) in enumerate(zip(texts, rows, strict=True)):
        for index, cell in enumerate(cells):
            if number and cell.name == "th" and row[index]:
                row[index] = f"**{row[index]}**"
        row.extend([""] * (width - len(row)))
    header, *body = texts
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    lines.extend("| " + " | ".join(r) + " |" for r in body)
    return "\n".join(lines)


def _html(walker: Walker, rows: list[list[Tag]]) -> str:
    parts = ["<table>"]
    for cells in rows:
        parts.append("<tr>")
        for cell in cells:
            tag = "th" if cell.name == "th" else "td"
            attrs = "".join(
                f' {name}="{_span(cell, name)}"'
                for name in ("colspan", "rowspan")
                if _span(cell, name) > 1
            )
            plain = _plain_text(cell)
            blocks = [] if plain is not None else walker.blocks(cell)
            if plain:
                parts.append(f"<{tag}{attrs}>{plain}</{tag}>")
            elif blocks:
                parts.append(f"<{tag}{attrs}>\n\n" + "\n\n".join(blocks) + f"\n\n</{tag}>")
            else:
                parts.append(f"<{tag}{attrs}></{tag}>")
        parts.append("</tr>")
    parts.append("</table>")
    return "\n".join(parts)
