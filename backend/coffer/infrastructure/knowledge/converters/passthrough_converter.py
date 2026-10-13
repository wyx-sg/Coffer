"""Passthrough converter for formats that are already text/Markdown.

Markdown, plain text, and source-code files are decoded as UTF-8 — no external
dependency, no engine. A Markdown or text upload keeps **one** frontmatter
(design "One frontmatter per upload"): its own block is split off, a second
block right under it (a Coffer source re-uploaded with an imported document's
block below) is merged in with its keys winning, and the keys travel as the
conversion's metadata so the source carries them. A Markdown file holding
``skynet-confluence-storage:v1`` markers has each marker converted to readable
Markdown, and the uploaded file is kept as the original on this Mac.
"""

from __future__ import annotations

import pathlib
from typing import Any

from coffer.domain.knowledge.converter import Conversion, ConversionIssue, derive_title
from coffer.infrastructure.knowledge.converters.confluence import (
    STORAGE_MARKER,
    expand_storage_markers,
)
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

#: Formats whose leading ``---`` block is a frontmatter. A YAML file's is not.
_MARKDOWN_FORMATS = frozenset({"md", "markdown", "mdx", "txt", "text"})

#: Keys Coffer writes itself on every source; an upload's own values are dropped.
_COFFER_KEYS = ("actor", "created_at", "updated_at")

#: An issue that does not make an import partial: the text is there, unrendered.
_NOT_PARTIAL = frozenset({"not_rendered"})

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
        if pathlib.PurePosixPath(filename).suffix.lower().lstrip(".") not in _MARKDOWN_FORMATS:
            return Conversion(
                markdown=text, title=derive_title(text, filename), converter="passthrough"
            )
        return markdown_conversion(text, filename)


def one_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """The upload's keys, merged into one mapping, and the body under them."""
    outer, body = split_frontmatter(text)
    inner: dict[str, Any] = {}
    if body.startswith("---"):
        inner, rest = split_frontmatter(body)
        if inner:
            body = rest
    merged = {**outer, **inner}
    for key in _COFFER_KEYS:
        merged.pop(key, None)
    description = merged.get("description")
    if description is not None and (
        not isinstance(description, str) or description.lstrip().startswith("---")
    ):
        merged.pop("description")
    return merged, body


def _first_heading(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return ""


def markdown_conversion(text: str, filename: str) -> Conversion:
    """A Markdown or text upload as one frontmatter and its body."""
    metadata, body = one_frontmatter(text)
    title = str(metadata.pop("title", "") or "").strip()
    title = title or _first_heading(body) or pathlib.PurePosixPath(filename).stem or "upload"
    issues: tuple[ConversionIssue, ...] = ()
    keeps_original: bool | None = None
    if STORAGE_MARKER in body:
        body, issues = expand_storage_markers(body)
        keeps_original = True
        partial = any(issue.kind not in _NOT_PARTIAL for issue in issues)
        metadata.update(
            {
                "representation": "markdown expanded from confluence storage markers",
                "import_status": "partial" if partial else "complete",
                "import_issues": [
                    {"kind": i.kind, "name": i.name, "reason": i.reason} for i in issues
                ],
            }
        )
    return Conversion(
        markdown=body,
        title=title,
        converter="passthrough",
        issues=issues,
        metadata=metadata,
        keeps_original=keeps_original,
    )
