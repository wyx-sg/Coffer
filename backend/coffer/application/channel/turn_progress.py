"""One line of tool progress, as a reader sees it.

Pure formatting split out of ``turn_render`` (which reached its size budget):
a tool call becomes ``⏳ Read · wedding.json`` — the tool, and the one detail
from its input that says what it is actually doing. In a group only the tool name
is shown (see "Render replies by the adapter's declared capabilities").
"""

from __future__ import annotations

_DESC_MAX_CHARS = 48


def _clip(text: str, limit: int = _DESC_MAX_CHARS) -> str:
    """Collapse whitespace and cap length so a descriptor stays one tidy line."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _basename(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1] if path else ""


def _host(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0]


def _describe_tool(tool_name: str, tool_input: object, *, chat_kind: str = "direct") -> str:
    """A short human descriptor of what a tool call is doing, drawn from its
    input — so channel progress reads '⏳ Bash · list the desktop' instead of a
    bare '⏳ Bash'.

    A group chat gets no descriptor at all: everyone in it reads the line, and the
    input can carry a command, a query or a path. In a direct chat only fields
    written to be read are used — never a raw command, and never a guess at "the
    first string argument", which for an unknown tool can be a token or a SQL
    statement. Anything else yields nothing.
    """
    if chat_kind == "group" or not isinstance(tool_input, dict):
        return ""

    def field_str(key: str) -> str:
        value = tool_input.get(key)
        return value if isinstance(value, str) else ""

    name = tool_name.lower()
    if name in ("bash", "shell", "exec"):
        return field_str("description")
    if name in ("read", "write", "edit", "multiedit", "notebookedit"):
        return _basename(field_str("file_path"))
    if name in ("grep", "glob"):
        return field_str("pattern")
    if name == "task":
        return field_str("description")
    if name == "webfetch":
        return _host(field_str("url"))
    if name == "websearch":
        return field_str("query")
    return ""


def _progress_line(mark: str, tool_name: str, descriptor: str) -> str:
    descriptor = _clip(descriptor)
    return f"{mark} {tool_name} · {descriptor}" if descriptor else f"{mark} {tool_name}"
