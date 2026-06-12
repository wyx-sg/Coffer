"""Passthrough converter for formats that are already text/markdown.

Markdown, plain text, and source-code files are decoded as UTF-8 and returned
unchanged (cleaning is applied by the caller). No external dependency.
"""

from __future__ import annotations

# Formats handled without any conversion engine. Source-code extensions are
# wrapped in a fenced block by the caller's cleaning step only if desired; here
# we pass the text through verbatim so grep/keyword see the raw content.
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
    """Implements ``MarkdownConverter`` for already-text formats."""

    def can_handle(self, fmt: str) -> bool:
        return fmt.lower().lstrip(".") in PASSTHROUGH_FORMATS

    async def convert(self, data: bytes, fmt: str) -> tuple[str, dict[str, object]]:
        text = data.decode("utf-8", errors="replace")
        return text, {"conversion_engine": "passthrough"}
