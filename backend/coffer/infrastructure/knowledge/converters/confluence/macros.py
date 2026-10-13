"""Confluence's own elements rewritten as plain HTML before the page becomes
Markdown (spec knowledge "Import a Confluence page as a readable source with
its attachments").

A macro is read for what a reader of the page sees, never dropped for being a
macro: a macro that only arranges its body — ``numberedheadings``, ``section``,
``column``, an ``expand`` — gives its body back, so a page wrapped whole in one
loses nothing; ``info``, ``note``, ``tip`` and ``warning`` become a quote that
says which; ``code`` and ``noformat`` keep their text and language; a
``plantuml`` diagram shows its source as code, and a draw.io diagram its
picture or a link that opens it. Only what Confluence
generates from the rest of the page — a table of contents, a child-page list —
is dropped, and said so. A macro Coffer does not know keeps its body when it has
one and is reported unsupported when it has none. Every outcome is recorded on
the conversion's :class:`Context`.
"""

from __future__ import annotations

from collections.abc import Callable

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString, PageElement

from coffer.domain.knowledge.converter import (
    ITEM_CONVERTED,
    ITEM_DROPPED,
    ITEM_KEPT,
    ITEM_MISSING,
    ITEM_UNSUPPORTED,
)
from coffer.infrastructure.knowledge.converters.confluence import diagrams
from coffer.infrastructure.knowledge.converters.confluence.context import Context

#: Macros that only arrange their body: the body is the content.
UNWRAP = frozenset(
    {
        "numberedheadings",
        "section",
        "column",
        "div",
        "span",
        "align",
        "center",
        "toc-zone",
        "excerpt",
        "details",
        "page-properties",
        "auimessage",
        "ui-tabs",
        "ui-tab",
        "localtab-group",
        "localtab",
        "deck",
        "card",
        "multiexcerpt",
        "multiexcerpt-macro",
    }
)
#: Content Confluence generates from elsewhere; there is nothing of the page in it.
GENERATED = frozenset(
    {
        "toc",
        "children",
        "pagetree",
        "recently-updated",
        "contributors",
        "contributors-summary",
        "content-by-label",
        "anchor",
        "easy-heading-free",
        "easy-heading",
        "livesearch",
        "create-from-template",
        "blog-posts",
    }
)
#: Panels: their kind is said in the quote they become.
PANELS = {
    "info": "Info",
    "note": "Note",
    "tip": "Tip",
    "warning": "Warning",
    "panel": "",
    "success": "Success",
    "error": "Error",
}
CODE = frozenset({"code", "noformat", "code-block"})
DRAWIO = frozenset({"drawio", "inc-drawio", "drawio-sketch", "gliffy"})
PLANTUML = frozenset({"plantuml", "plantumlrender", "plantuml-macro"})
HTML = frozenset({"html", "html-bobswift", "html-include"})


def _param(macro: Tag, name: str) -> str:
    for child in macro.find_all("ac:parameter", recursive=False):
        if (child.get("ac:name") or "") == name:
            return child.get_text().strip()
    return ""


def _body(macro: Tag, kind: str) -> Tag | None:
    found = macro.find(f"ac:{kind}-text-body", recursive=False)
    return found if isinstance(found, Tag) else None


def _plain(macro: Tag) -> str:
    body = _body(macro, "plain")
    return body.get_text() if body is not None else ""


def _p(soup: BeautifulSoup, *parts: object) -> Tag:
    para = soup.new_tag("p")
    for part in parts:
        para.append(part if isinstance(part, Tag) else NavigableString(str(part)))
    return para


def _em(soup: BeautifulSoup, text: str) -> Tag:
    tag = soup.new_tag("em")
    tag.string = text
    return tag


def _a(soup: BeautifulSoup, href: str, text: str) -> Tag:
    # No link when the conversion keeps no files (a page read, not imported).
    tag = soup.new_tag("a", href=href) if href else soup.new_tag("span")
    tag.string = text
    return tag


def _code(soup: BeautifulSoup, text: str, language: str) -> Tag:
    pre = soup.new_tag("pre")
    code = soup.new_tag("code")
    if language:
        code["class"] = f"language-{language}"
    code.string = text.strip("\n")
    pre.append(code)
    return pre


#: What a macro becomes: elements and text.
Node = PageElement


def _children(tag: Tag | None) -> list[Node]:
    return list(tag.contents) if tag is not None else []


Handler = Callable[[BeautifulSoup, Tag, str, Context], list[Node]]


def _unwrap(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    ctx.macro(name, ITEM_CONVERTED, "its body is kept as the page's text")
    return _children(_body(m, "rich"))


def _panel(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    quote = soup.new_tag("blockquote")
    label = PANELS.get(name, "")
    title = _param(m, "title")
    head = ": ".join(t for t in (label, title) if t)
    if head:
        strong = soup.new_tag("strong")
        strong.string = head
        quote.append(_p(soup, strong))
    for child in _children(_body(m, "rich")):
        quote.append(child)
    ctx.macro(name, ITEM_CONVERTED)
    return [quote]


def _expand(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    strong = soup.new_tag("strong")
    strong.string = _param(m, "title") or "Details"
    ctx.macro(name, ITEM_CONVERTED, "shown open")
    return [_p(soup, strong), *_children(_body(m, "rich"))]


def _code_macro(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    ctx.macro(name, ITEM_CONVERTED)
    nodes: list[Node] = []
    title = _param(m, "title")
    if title:
        nodes.append(_p(soup, _em(soup, title)))
    nodes.append(_code(soup, _plain(m), _param(m, "language").lower()))
    return nodes


def _plantuml(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    text = _plain(m).strip()
    if not text:
        ctx.macro(name, ITEM_UNSUPPORTED, "the diagram has no source in the page")
        ctx.partial = True
        return [_p(soup, _em(soup, "[PlantUML diagram with no source in the page]"))]
    ctx.macro(name, ITEM_CONVERTED, "shown as its source; no picture drawn")
    return [_code(soup, text, "plantuml")]


def _drawio(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    diagram = _param(m, "diagramName") or _param(m, "name")
    if not diagram:
        ctx.macro(name, ITEM_UNSUPPORTED, "names no diagram")
        return [_p(soup, _em(soup, f"[{name} diagram that names no file]"))]
    for candidate in (f"{diagram}.png", f"{diagram}.svg", f"{diagram}.drawio.png"):
        picture = ctx.attachment(candidate, reason_missing="") if ctx.has(candidate) else None
        if picture:
            ctx.macro(name, ITEM_KEPT, diagram)
            return [soup.new_tag("img", src=picture, alt=diagram)]
    reason = "the diagram's picture was not downloaded with the page"
    ctx.macro(name, ITEM_MISSING, reason)
    ctx.attachment(f"{diagram}.png", reason_missing=reason)
    return [_p(soup, _em(soup, f"[draw.io diagram {diagram}: not archived]"))]


def _html(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    markup = _plain(m)
    nodes: list[Node] = []
    for xml in diagrams.from_html(markup):
        ctx.macro(name, ITEM_CONVERTED, "draw.io diagram in the page; shown as a viewer link")
        nodes.append(_p(soup, _a(soup, diagrams.viewer_link(xml), "draw.io diagram")))
    for src in diagrams.embeds(markup):
        elsewhere = diagrams.remote_kind(src) or "a page outside Confluence"
        ctx.macro(name, ITEM_MISSING, f"embeds {elsewhere}; needs its owner's access, not archived")
        nodes.append(
            _p(soup, _em(soup, f"Embedded {elsewhere} (not archived): "), _a(soup, src, src))
        )
    rest = BeautifulSoup(markup, "html.parser")
    for tag in rest.find_all(["script", "style", "iframe", "object", "embed", "noscript", "link"]):
        tag.decompose()
    for tag in [t for t in rest.find_all(True) if t.has_attr("data-mxgraph")]:
        tag.decompose()
    if rest.get_text(" ").strip():
        ctx.macro(name, ITEM_CONVERTED, "its HTML kept as text; scripts and embeds removed")
        nodes += list(rest.contents)
    elif not nodes:
        ctx.macro(name, ITEM_DROPPED, "holds no text")
    return nodes


def _generated(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    ctx.macro(name, ITEM_DROPPED, "generated by Confluence from the rest of the page")
    return []


def _status(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    ctx.macro(name, ITEM_CONVERTED)
    return [NavigableString(f"[{_param(m, 'title') or _param(m, 'colour') or 'status'}]")]


def _jira(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    key = _param(m, "key")
    if key:
        ctx.macro(name, ITEM_CONVERTED, "the issue key is kept")
        return [NavigableString(key)]
    ctx.macro(name, ITEM_UNSUPPORTED, "an issue query, not kept")
    ctx.partial = True
    return [_em(soup, "[Jira issue list: not archived]")]


def _unknown(soup: BeautifulSoup, m: Tag, name: str, ctx: Context) -> list[Node]:
    body = _body(m, "rich")
    if body is not None:
        ctx.macro(name, ITEM_CONVERTED, "an unknown macro; its body is kept")
        return _children(body)
    text = _plain(m)
    if text.strip():
        ctx.macro(name, ITEM_CONVERTED, "an unknown macro; its text is kept")
        return [_code(soup, text, "")]
    ctx.macro(name, ITEM_UNSUPPORTED, "an unknown macro with no body")
    ctx.partial = True
    return [_p(soup, _em(soup, f"[Confluence macro {name}: not supported]"))]


def handler(name: str) -> Handler:
    if name in UNWRAP:
        return _unwrap
    if name in GENERATED:
        return _generated
    if name in PANELS:
        return _panel
    if name == "expand":
        return _expand
    if name in CODE:
        return _code_macro
    if name in PLANTUML:
        return _plantuml
    if name in DRAWIO:
        return _drawio
    if name in HTML:
        return _html
    if name == "status":
        return _status
    if name == "jira":
        return _jira
    return _unknown


def rewrite(soup: BeautifulSoup, ctx: Context) -> None:
    """Replace every macro in ``soup`` with what it shows, innermost first."""
    for macro in reversed(soup.find_all(["ac:structured-macro", "ac:macro"])):
        if macro.parent is None:
            continue
        name = str(macro.get("ac:name") or "").strip().lower() or "unnamed"
        nodes = handler(name)(soup, macro, name, ctx)
        for node in nodes:
            macro.insert_before(node)
        macro.decompose()


__all__ = ["CODE", "DRAWIO", "GENERATED", "HTML", "PANELS", "PLANTUML", "UNWRAP", "rewrite"]
