"""Confluence macros (``ac:structured-macro``) → Markdown, per the design §5 table.

Layout macros are unwrapped, navigation is dropped, panels become blockquotes,
code keeps its text verbatim and its language, diagrams are kept as their
sources, and an unknown macro keeps its body and is listed ``unsupported_macro``
— a macro's text is never dropped silently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, Tag

from coffer.infrastructure.knowledge.converters.confluence import diagrams
from coffer.infrastructure.knowledge.converters.confluence.kept import (
    NOT_RENDERED,
    UNSUPPORTED,
    asset_link,
)
from coffer.infrastructure.knowledge.converters.confluence.text import (
    code_span,
    escape_text,
    fence,
    quote,
)

if TYPE_CHECKING:
    from coffer.infrastructure.knowledge.converters.confluence.storage import Walker

MACRO_TAGS = frozenset({"ac:structured-macro", "ac:macro"})
UNWRAPPED = frozenset({"numberedheadings", "easy-heading-free", "section", "column", "details"})
NAVIGATION = frozenset({"toc", "children", "pagetree", "anchor"})
INLINE = frozenset({"status", "jira", "anchor"})
PANELS = {"info": "Info", "note": "Note", "tip": "Tip", "warning": "Warning", "panel": "Panel"}
CODE = frozenset({"code", "noformat"})
DRAWIO = frozenset({"drawio", "inc-drawio"})


def is_macro(tag: Tag) -> bool:
    return tag.name in MACRO_TAGS


def macro_name(tag: Tag) -> str:
    return str(tag.get("ac:name") or "").strip().lower()


def is_inline(tag: Tag) -> bool:
    return macro_name(tag) in INLINE


def parameters(tag: Tag) -> dict[str, str]:
    found: dict[str, str] = {}
    for param in tag.find_all("ac:parameter", recursive=False):
        found[str(param.get("ac:name") or "")] = param.get_text().strip()
    return found


def rich_body(tag: Tag) -> Tag | None:
    body = tag.find("ac:rich-text-body", recursive=False)
    return body if isinstance(body, Tag) else None


def plain_body(tag: Tag) -> str | None:
    body = tag.find("ac:plain-text-body", recursive=False)
    return body.get_text() if isinstance(body, Tag) else None


# -- blocks ------------------------------------------------------------------


def block(walker: Walker, tag: Tag) -> list[str]:
    name = macro_name(tag)
    params = parameters(tag)
    body = rich_body(tag)
    if name in UNWRAPPED:
        return walker.blocks(body) if body is not None else []
    if name in NAVIGATION:
        return []
    if name == "expand":
        title = escape_text(params.get("title") or "Details")
        inner = walker.blocks(body) if body is not None else []
        return [f"**{title}**", *inner]
    if name in PANELS:
        label = (params.get("title") if name == "panel" else None) or PANELS[name]
        inner = walker.blocks(body) if body is not None else []
        return [quote([f"**{escape_text(label)}:**", *inner])]
    if name in CODE:
        language = params.get("language", "") if name == "code" else ""
        return [fence(plain_body(tag) or "", language.strip().split()[0] if language else "")]
    if name == "plantuml":
        return _plantuml(walker, tag)
    if name in DRAWIO:
        return _drawio(walker, name, params)
    if name == "html":
        return _html(walker, plain_body(tag) or "")
    if name in INLINE:
        text = inline(walker, tag)
        return [text] if text else []
    return _unknown(walker, tag, name, body)


def _unknown(walker: Walker, tag: Tag, name: str, body: Tag | None) -> list[str]:
    label = name or "unnamed"
    if body is not None:
        walker.kept.issue(UNSUPPORTED, label, "shown as its body only")
        return walker.blocks(body)
    text = plain_body(tag)
    if text and text.strip():
        walker.kept.issue(UNSUPPORTED, label, "shown as its text only")
        return [fence(text)]
    walker.kept.issue(UNSUPPORTED, label, "a macro Coffer does not read; not kept")
    return [f"*The “{escape_text(label)}” macro was not kept.*"]


def _plantuml(walker: Walker, tag: Tag) -> list[str]:
    text = plain_body(tag) or ""
    kept = walker.kept
    if kept.keep_files:
        name = kept.diagram("puml", text.encode("utf-8"))
        label = name or kept.next_diagram_label()
    else:
        name, label = None, kept.next_diagram_label()
    kept.issue(NOT_RENDERED, name or label, "PlantUML is kept as its source; it is not drawn")
    out = [fence(text, "plantuml")]
    if name:
        out.append(f"[Diagram source: {name}]({asset_link(name)})")
    return out


def _drawio(walker: Walker, name: str, params: dict[str, str]) -> list[str]:
    kept = walker.kept
    diagram = params.get("diagramName") or params.get("diagramname") or ""
    if not diagram:
        kept.issue(UNSUPPORTED, name, "a draw.io macro naming no diagram")
        return ["*A draw.io diagram naming no attachment was not kept.*"]
    other_page = name == "inc-drawio"
    out: list[str] = []
    picture = f"{diagram}.png"
    if kept.has_attachment(picture) or not kept.keep_files:
        shown = kept.attachment(picture, other_page=other_page)
        if shown:
            out.append(f"![{escape_text(diagram)}]({asset_link(shown)})")
    source = next(
        (c for c in (diagram, f"{diagram}.drawio") if kept.has_attachment(c)),
        diagram,
    )
    wanted = source if source.endswith(".drawio") else f"{source}.drawio"
    kept_source = kept.attachment(source, other_page=other_page, wanted=wanted)
    if kept_source:
        out.append(f"[Diagram source: {kept_source}]({asset_link(kept_source)})")
    elif not out:
        out.append(f"*Diagram not kept: {escape_text(diagram)}*")
    return out


def _html(walker: Walker, markup: str) -> list[str]:
    kept = walker.kept
    soup = BeautifulSoup(markup, "html.parser")
    out: list[str] = []
    for element in soup.find_all(None, {"data-mxgraph": True}):
        out.append(diagrams.mxgraph(kept, str(element.get("data-mxgraph") or "")))
    for element in soup.find_all(["iframe", "a"]):
        url = str(element.get("src") or element.get("href") or "")
        if url and diagrams.is_diagram_url(url):
            out.append(diagrams.diagram_url(kept, url))
    if out:
        return out
    kept.issue(UNSUPPORTED, "html", "an HTML block; not kept")
    return ["*An HTML block was not kept.*"]


# -- inline ------------------------------------------------------------------


def inline(walker: Walker, tag: Tag) -> str:
    name = macro_name(tag)
    params = parameters(tag)
    if name == "status":
        title = params.get("title") or params.get("colour") or ""
        return code_span(title)
    if name == "jira":
        key = params.get("key")
        if key:
            return escape_text(key)
        query = params.get("jqlQuery") or params.get("jql") or ""
        walker.kept.issue(UNSUPPORTED, "jira", "a Jira query is shown as its text only")
        return f"Jira issues: {code_span(query)}" if query else "Jira issues"
    return ""
