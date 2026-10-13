"""Confluence references: ``ac:image``, ``ac:link`` and ``ac:task-list``.

A picture attached to the page is kept and linked as ``coffer-asset:<name>``;
one the export does not carry (or that lives on another page) is listed
``missing_attachment``; a remote picture becomes a plain link, never fetched,
and is listed ``external_image``. A link to a page, attachment or person
becomes its text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bs4 import Tag

from coffer.infrastructure.knowledge.converters.confluence.kept import asset_link
from coffer.infrastructure.knowledge.converters.confluence.text import (
    SPACE,
    escape_text,
    finish_paragraph,
    link,
)

if TYPE_CHECKING:
    from coffer.infrastructure.knowledge.converters.confluence.storage import Walker

_OTHER_CONTENT = ("ri:page", "ri:blog-post", "ri:content-entity")


def _alt(text: str) -> str:
    return SPACE.sub(" ", text).replace("[", "(").replace("]", ")").strip()


def _attr(tag: Tag | None, name: str) -> str:
    if tag is None:
        return ""
    return str(tag.get(name) or "").strip()


def image(walker: Walker, tag: Tag) -> str:
    kept = walker.kept
    alt = _attr(tag, "ac:alt") or _attr(tag, "ac:title")
    attachment = tag.find("ri:attachment")
    if isinstance(attachment, Tag):
        filename = _attr(attachment, "ri:filename")
        if not filename:
            return ""
        owner = attachment.find(_OTHER_CONTENT)
        other_page = isinstance(owner, Tag) and _attr(owner, "ri:content-title") not in (
            "",
            kept.page_title,
        )
        if isinstance(owner, Tag) and not _attr(owner, "ri:content-title"):
            other_page = True
        name = kept.attachment(filename, other_page=other_page)
        if name:
            return f"![{_alt(alt or filename)}]({asset_link(name)})"
        return f"*Picture not kept: {escape_text(filename)}*"
    remote = tag.find("ri:url")
    if isinstance(remote, Tag):
        return remote_picture(walker, _attr(remote, "ri:value"), alt)
    return ""


def remote_picture(walker: Walker, url: str, alt: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return ""
    walker.kept.external_image(url)
    return link(f"Picture: {escape_text(_alt(alt))}" if alt else "Picture", url)


def plain_image(walker: Walker, tag: Tag) -> str:
    return remote_picture(walker, _attr(tag, "src"), _attr(tag, "alt"))


def link_text(walker: Walker, tag: Tag) -> str:
    rich = tag.find("ac:link-body")
    if isinstance(rich, Tag):
        text = finish_paragraph(walker.inline_children(rich), " ")
        if text:
            return text
    plain = tag.find("ac:plain-text-link-body")
    if isinstance(plain, Tag) and plain.get_text().strip():
        return escape_text(SPACE.sub(" ", plain.get_text()).strip())
    target = next(
        (c for c in tag.children if isinstance(c, Tag) and c.name.startswith("ri:")), None
    )
    if target is None:
        return escape_text(_attr(tag, "ac:anchor"))
    if target.name in ("ri:page", "ri:blog-post"):
        return escape_text(_attr(target, "ri:content-title"))
    if target.name == "ri:attachment":
        return escape_text(_attr(target, "ri:filename"))
    if target.name == "ri:user":
        return "@" + escape_text(_attr(target, "ri:username") or "user")
    if target.name == "ri:space":
        return escape_text(_attr(target, "ri:space-key"))
    return escape_text(_attr(tag, "ac:anchor"))


def task_list(walker: Walker, tag: Tag) -> list[str]:
    items: list[str] = []
    for task in tag.find_all("ac:task", recursive=False):
        status = task.find("ac:task-status")
        done = isinstance(status, Tag) and status.get_text().strip().lower() == "complete"
        body = task.find("ac:task-body")
        text = finish_paragraph(walker.inline_children(body), " ") if isinstance(body, Tag) else ""
        items.append(f"- [{'x' if done else ' '}] {text}".rstrip())
    return ["\n".join(items)] if items else []
