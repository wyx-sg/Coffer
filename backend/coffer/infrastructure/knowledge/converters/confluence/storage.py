"""A Confluence page's storage format, read as the XHTML it is and written out
as readable Markdown (spec knowledge "Import a Confluence page as a readable
source with its attachments").

The storage format is the page as Confluence keeps it: XHTML plus Confluence's
own ``ac:`` elements (macros, pictures, links) and ``ri:`` references. It is
read in three steps:

1. **Parse.** ``CDATA`` sections — a ``code`` macro's text, an ``html``
   macro's markup — are taken out first and put back as escaped text, so a
   ``<module>`` inside a shell command is text and never a tag, on every Python
   version's parser.
2. **Rewrite.** Every macro becomes what a reader of the page sees
   (``macros.py``), every picture and attachment link points at the file kept
   beside the source, and Confluence's layout wrappers give back their content.
3. **Write Markdown.** A table with a header row and one line per cell becomes
   a Markdown table; any other — merged cells, lists or code in a cell, no
   header row — stays a small HTML table with only structural attributes, which
   every Markdown reader shows and which the Knowledge page renders through its
   sanitiser. Nothing of the page is written as Confluence XML.
"""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
from markdownify import MarkdownConverter

from coffer.infrastructure.knowledge.converters.confluence import diagrams, macros
from coffer.infrastructure.knowledge.converters.confluence.context import Context

_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
_BLOCKS = frozenset(
    {"ul", "ol", "pre", "blockquote", "table", "h1", "h2", "h3", "h4", "h5", "h6", "hr"}
)
#: Attributes an HTML table keeps; everything else (classes, styles, ids) goes.
_KEEP_ATTRS = {
    "a": ("href", "title"),
    "img": ("src", "alt", "title"),
    "td": ("colspan", "rowspan"),
    "th": ("colspan", "rowspan"),
    "code": ("class",),
}
_TABLE_MARK = "COFFERHTMLTABLE{}X"
_TABLE_MARK_RE = re.compile(r"^COFFERHTMLTABLE(\d+)X$", re.MULTILINE)


def parse(storage: str) -> BeautifulSoup:
    """The storage XHTML as a tree, its ``CDATA`` sections as plain text."""
    protected = _CDATA.sub(
        lambda m: f"<coffer-cdata>{html.escape(m.group(1))}</coffer-cdata>", storage
    )
    return BeautifulSoup(f"<coffer-root>{protected}</coffer-root>", "html.parser")


def _image(soup: BeautifulSoup, tag: Tag, ctx: Context) -> None:
    alt = str(tag.get("ac:alt") or tag.get("ac:title") or "")
    attachment = tag.find("ri:attachment")
    url = tag.find("ri:url")
    if isinstance(attachment, Tag):
        name = str(attachment.get("ri:filename") or "")
        other = attachment.find("ri:page")
        if isinstance(other, Tag):
            page = str(other.get("ri:content-title") or "another page")
            ctx.attachment(name, reason_missing=f"an attachment of the page {page!r}")
            link = None
        else:
            link = ctx.attachment(name, reason_missing="not downloaded with the page")
        if link:
            tag.replace_with(soup.new_tag("img", src=link, alt=alt or name))
            return
        em = soup.new_tag("em")
        em.string = f"[Picture not archived: {name}]"
        tag.replace_with(em)
        return
    if isinstance(url, Tag):
        src = str(url.get("ri:value") or "")
        ctx.attachment(src, reason_missing="a picture at an outside address; not downloaded")
        link_tag = soup.new_tag("a", href=src)
        link_tag.string = f"[Picture not archived: {alt or src}]"
        tag.replace_with(link_tag)
        return
    tag.decompose()


def _link(soup: BeautifulSoup, tag: Tag, ctx: Context) -> None:
    body = tag.find(["ac:link-body", "ac:plain-text-link-body"])
    text = body.get_text().strip() if isinstance(body, Tag) else ""
    attachment = tag.find("ri:attachment")
    page = tag.find("ri:page")
    if isinstance(attachment, Tag) and not isinstance(attachment.find("ri:page"), Tag):
        name = str(attachment.get("ri:filename") or "")
        link = ctx.attachment(name, reason_missing="not downloaded with the page")
        if link:
            anchor = soup.new_tag("a", href=link)
            anchor.string = text or name
            tag.replace_with(anchor)
            return
        tag.replace_with(NavigableString(f"{text or name} (attachment not archived)"))
        return
    if isinstance(page, Tag):
        title = str(page.get("ri:content-title") or "")
        tag.replace_with(NavigableString(text or title))
        return
    if tag.find("ri:user") is not None:
        tag.replace_with(NavigableString(text or "[a person]"))
        return
    tag.replace_with(NavigableString(text))


def _task_list(soup: BeautifulSoup, tag: Tag) -> None:
    items = soup.new_tag("ul")
    for task in tag.find_all("ac:task", recursive=False):
        done = task.find("ac:task-status")
        body = task.find("ac:task-body")
        li = soup.new_tag("li")
        mark = "[x] " if done is not None and done.get_text().strip() == "complete" else "[ ] "
        li.append(NavigableString(mark))
        if isinstance(body, Tag):
            for child in list(body.contents):
                li.append(child)
        items.append(li)
    tag.replace_with(items)


def _viewer_links(soup: BeautifulSoup, ctx: Context) -> None:
    """A draw.io viewer link carrying its diagram (``#R``) keeps the diagram
    as a file and points at it, instead of a URL thousands of characters long."""
    for anchor in soup.find_all("a", href=True):
        xml = diagrams.from_viewer_link(str(anchor["href"]))
        if xml is None:
            continue
        n = ctx.next_number("diagram")
        link = ctx.add_file(f"diagram-{n}.drawio", xml.encode("utf-8"))
        ctx.macro("draw.io link", "source_kept", "the diagram the link carried; source kept", link)
        if link:
            anchor["href"] = link
        anchor.string = f"draw.io diagram (diagram-{n}.drawio)"


def _confluence_elements(soup: BeautifulSoup, ctx: Context) -> None:
    for tag in soup.find_all("ac:image"):
        _image(soup, tag, ctx)
    for tag in soup.find_all("ac:link"):
        if tag.parent is not None:
            _link(soup, tag, ctx)
    for tag in soup.find_all("ac:task-list"):
        _task_list(soup, tag)
    for tag in soup.find_all(["ac:emoticon", "ac:placeholder", "ac:parameter", "colgroup"]):
        tag.decompose()
    for tag in soup.find_all("time"):
        tag.replace_with(NavigableString(str(tag.get("datetime") or tag.get_text())))
    # Every remaining Confluence wrapper — a layout, a comment marker, a
    # leftover body — gives back its content.
    for tag in soup.find_all(re.compile(r"^(ac:|ri:|coffer-cdata$)")):
        if tag.parent is not None and tag.name != "coffer-root":
            tag.unwrap()
    for tag in soup.find_all(["p", "div", "span"]):
        if tag.parent is not None and not tag.get_text(strip=True) and not tag.find(["img", "a"]):
            tag.decompose()
    for text in soup.find_all(string=True):
        if "\xa0" in text:
            text.replace_with(text.replace("\xa0", " "))


def _rows(table: Tag) -> list[Tag]:
    return [r for r in table.find_all("tr") if r.find_parent("table") is table]


def _simple(table: Tag) -> bool:
    """Whether ``table`` reads as a Markdown table: a header row of ``th``,
    no merged cells, and one line of inline content per cell."""
    rows = _rows(table)
    if not rows or table.find("table") is not None:
        return False
    if not rows[0].find_all(["th", "td"], recursive=False) or rows[0].find("td", recursive=False):
        return False
    for row in rows:
        for cell in row.find_all(["th", "td"], recursive=False):
            if str(cell.get("colspan") or "1") != "1" or str(cell.get("rowspan") or "1") != "1":
                return False
            if cell.find(_BLOCKS) is not None or cell.find("br") is not None:
                return False
            if len(cell.find_all("p")) > 1:
                return False
    return True


def _clean(tag: Tag) -> None:
    for child in [tag, *tag.find_all(True)]:
        keep = _KEEP_ATTRS.get(child.name, ())
        attrs = {k: v for k, v in child.attrs.items() if k in keep}
        for span in ("colspan", "rowspan"):
            if str(attrs.get(span, "1")) == "1":
                attrs.pop(span, None)
        if child.name == "code" and "class" in attrs:
            classes = attrs["class"] if isinstance(attrs["class"], list) else [attrs["class"]]
            languages = [str(c) for c in classes if str(c).startswith("language-")]
            if languages:
                attrs["class"] = " ".join(languages)
            else:
                attrs.pop("class")
        child.attrs = attrs
    for wrapper in tag.find_all(["div", "span"]):
        wrapper.unwrap()


def _html_tables(soup: BeautifulSoup) -> list[str]:
    """Every table that does not read as a Markdown table, replaced by a mark
    and kept as clean HTML, outermost first."""
    kept: list[str] = []
    for table in soup.find_all("table"):
        if table.parent is None or table.find_parent("table") is not None or _simple(table):
            continue
        _clean(table)
        kept.append(str(table))
        mark = soup.new_tag("p")
        mark.string = _TABLE_MARK.format(len(kept) - 1)
        table.replace_with(mark)
    return kept


class _Writer(MarkdownConverter):
    def convert_coffer_root(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        return text


def _language(el: Tag) -> str:
    code = el.find("code")
    raw = code.get("class") if isinstance(code, Tag) else None
    classes = raw.split() if isinstance(raw, str) else list(raw or [])
    for cls in classes:
        if str(cls).startswith("language-"):
            return str(cls)[len("language-") :]
    return ""


def to_markdown(soup: BeautifulSoup) -> str:
    tables = _html_tables(soup)
    # What is left are Markdown tables, where a ``|`` in a cell ends the cell.
    for table in soup.find_all("table"):
        for cell_text in table.find_all(string=True):
            if "|" in cell_text:
                cell_text.replace_with(cell_text.replace("|", "\\|"))
    text: str = _Writer(
        heading_style="ATX",
        bullets="-",
        escape_underscores=False,
        escape_asterisks=False,
        code_language_callback=_language,
    ).convert_soup(soup)
    text = _TABLE_MARK_RE.sub(lambda m: tables[int(m.group(1))], text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def convert(storage: str, ctx: Context) -> str:
    """The page's storage as readable Markdown; what it kept and left out is
    recorded on ``ctx``."""
    soup = parse(storage)
    macros.rewrite(soup, ctx)
    _confluence_elements(soup, ctx)
    _viewer_links(soup, ctx)
    return to_markdown(soup)


__all__ = ["convert", "parse", "to_markdown"]
