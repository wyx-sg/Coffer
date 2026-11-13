"""Passthrough converter for formats that are already text/Markdown.

Markdown, plain text, and source-code files are decoded as UTF-8 and returned
unchanged — no external dependency, no engine.

Two things in a Markdown upload are read rather than passed on, so the source
it becomes is not double-fronted or full of markup a reader cannot read (spec
knowledge "Fill frontmatter on converted material" and "Import a Confluence
page as a readable source with its attachments"):

* **Its own frontmatter.** A file that opens with a ``---`` block hands its
  keys to the source's frontmatter and its title to the source's title; the
  body is what follows the block. Without this the block would land in the
  body under a second one, and its text in the description.
* **Confluence storage markers.** What a Confluence export left as storage
  inside an HTML comment is converted where it stands (``confluence.markers``);
  the uploaded file, markers and all, is kept on this Mac as its original.
"""

from __future__ import annotations

from coffer.domain.knowledge.converter import (
    BODY_CONVERTED,
    BODY_PARTIAL,
    Conversion,
    ImportReport,
    derive_title,
)
from coffer.infrastructure.knowledge.converters.confluence import markers
from coffer.infrastructure.knowledge.converters.confluence.context import Context
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

_MARKDOWN = frozenset({"md", "markdown", "mdx"})

# Formats handled without any conversion engine. Source-code extensions are
# passed through verbatim (not fenced): what is submitted is the file's own text.
PASSTHROUGH_FORMATS = frozenset(
    {
        "md",
        "markdown",
        "mdx",
        "txt",
        "text",
        "rst",
        "py",
        "js",
        "ts",
        "tsx",
        "jsx",
        "java",
        "go",
        "rs",
        "rb",
        "c",
        "h",
        "cpp",
        "hpp",
        "cs",
        "sh",
        "bash",
        "zsh",
        "sql",
        "yaml",
        "yml",
        "toml",
        "ini",
        "cfg",
        "json",
        "log",
    }
)


class PassthroughConverter:
    """Implements ``Converter`` for already-text formats."""

    def can_handle(self, fmt: str) -> bool:
        return fmt.lower().lstrip(".") in PASSTHROUGH_FORMATS

    async def convert(self, data: bytes, filename: str) -> Conversion:
        text = data.decode("utf-8", errors="replace")
        if filename.rpartition(".")[2].lower() not in _MARKDOWN:
            return Conversion(
                markdown=text, title=derive_title(text, filename), converter="passthrough"
            )
        meta, body = split_frontmatter(text.replace("\r\n", "\n"))
        title = str(meta.get("title") or "").strip() or derive_title(body, filename)
        if not markers.has_markers(body):
            return Conversion(markdown=body, title=title, converter="passthrough", metadata=meta)
        ctx = Context()
        expanded = markers.expand(body, ctx)
        return Conversion(
            markdown=expanded.markdown,
            title=title,
            converter="passthrough",
            metadata=meta,
            files=tuple(ctx.files),
            report=ImportReport(
                body=BODY_PARTIAL if ctx.partial else BODY_CONVERTED,
                attachments=tuple(ctx.attachment_items),
                macros=tuple(reversed(ctx.macro_items)),
            ),
        )
