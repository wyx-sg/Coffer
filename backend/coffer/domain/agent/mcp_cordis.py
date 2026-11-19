"""DeepSeek Harness MCP rows in a Cordis patch file — pure text transforms.

DeepSeek Harness (``dsh``) composes its plugin tree from YAML patch layers. The
home-level layer ``$DSH_HOME/cordis.patch.yml`` applies to every profile and
outranks each profile's own layer, so it is where Coffer's ``coffer`` MCP row
belongs: one ``insert`` of a ``@deepseek-ai/dsh-mcp-client`` row.

The file is the person's own and may hold ``!!js`` expressions, comments and
rows of other plugins; no YAML library round-trips that faithfully. So Coffer
never re-serialises it. Its row lives in a block between two marker comments,
and every write replaces that block as text and leaves every other byte alone
(ADR writing-agent-native-config-safely: an edit preserves what it does not
own). Reading — the listing and the reconciler's comparison — parses the whole
file with a loader that keeps ``!!js`` values as plain strings.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

import yaml

from coffer.domain.errors import ConfigFileFormatInvalid

#: The plugin every MCP server row names.
MCP_CLIENT_PLUGIN = "@deepseek-ai/dsh-mcp-client"
#: The row id Coffer's own entry carries (unique within the patch stack).
COFFER_ROW_ID = "coffer-mcp"

BLOCK_START = "# >>> coffer: managed by Coffer, edits inside this block are replaced >>>"
BLOCK_END = "# <<< coffer <<<"

_BLOCK_RE = re.compile(
    r"(?:^|\n)" + re.escape(BLOCK_START) + r"\n.*?" + re.escape(BLOCK_END) + r"[^\n]*(?:\n|$)",
    re.DOTALL,
)


class _TolerantLoader(yaml.SafeLoader):
    """A safe loader that reads a ``!!js`` (or any other local) tag's value as
    its plain source text instead of refusing the document."""


def _tag_as_text(loader: yaml.SafeLoader, _suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_mapping(node, deep=True)  # type: ignore[arg-type]


_TolerantLoader.add_multi_constructor("tag:yaml.org,2002:js", _tag_as_text)  # type: ignore[no-untyped-call]
_TolerantLoader.add_multi_constructor("!", _tag_as_text)  # type: ignore[no-untyped-call]


def load_patches(text: str) -> list[Any]:
    """The patch file as a list of patch items (``[]`` for an empty file).

    Raises ``ConfigFileFormatInvalid`` for text that does not parse or whose top
    level is not a list."""
    if not text.strip():
        return []
    try:
        data = yaml.load(text, Loader=_TolerantLoader)
    except yaml.YAMLError as e:
        raise ConfigFileFormatInvalid("yaml", str(e)) from e
    if data is None:
        return []
    if not isinstance(data, list):
        raise ConfigFileFormatInvalid("yaml", "top-level value must be a list of patches")
    return data


def mcp_rows(text: str) -> list[dict[str, Any]]:
    """Every ``@deepseek-ai/dsh-mcp-client`` row the patch file inserts, in order."""
    rows: list[dict[str, Any]] = []
    for item in load_patches(text):
        if not isinstance(item, Mapping):
            continue
        inserted = item.get("insert")
        if not isinstance(inserted, list):
            continue
        for row in inserted:
            if isinstance(row, Mapping) and row.get("name") == MCP_CLIENT_PLUGIN:
                rows.append(dict(row))
    return rows


def row_server_name(row: Mapping[str, Any]) -> str:
    """The server name a row registers (its ``config.serverName``, else its id)."""
    config = row.get("config")
    if isinstance(config, Mapping) and config.get("serverName"):
        return str(config["serverName"])
    return str(row.get("id", ""))


def coffer_row(text: str) -> dict[str, Any] | None:
    """Coffer's own row — the one registering the ``coffer`` server — or ``None``."""
    for row in mcp_rows(text):
        if row.get("id") == COFFER_ROW_ID or row_server_name(row) == "coffer":
            return row
    return None


def plain_entry(row: Mapping[str, Any]) -> dict[str, Any]:
    """A DeepSeek Harness MCP row as the plain entry shape the parser reads:
    its ``config`` fields, ``streamable-http`` as a remote type, and ``enabled``
    from the row's ``disabled`` flag."""
    config = row.get("config")
    entry: dict[str, Any] = dict(config) if isinstance(config, Mapping) else {}
    entry.pop("serverName", None)
    transport = str(entry.pop("transport", "stdio")).lower()
    if transport != "stdio":
        entry["type"] = "http"
    if "disabled" in row:
        entry["enabled"] = not bool(row.get("disabled"))
    return entry


def _quote(value: str) -> str:
    """A YAML single-quoted scalar: safe for any path or argument."""
    return "'" + value.replace("'", "''") + "'"


def render_block(command: str, args: Sequence[str]) -> str:
    """Coffer's managed block: one ``insert`` patch with its one MCP row."""
    arg_list = "[" + ", ".join(_quote(a) for a in args) + "]"
    return "\n".join(
        [
            BLOCK_START,
            "- insert:",
            f"    - id: {COFFER_ROW_ID}",
            f"      name: {_quote(MCP_CLIENT_PLUGIN)}",
            "      config:",
            "        serverName: coffer",
            "        transport: stdio",
            f"        command: {_quote(command)}",
            f"        args: {arg_list}",
            BLOCK_END,
            "",
        ]
    )


def strip_block(text: str) -> str:
    """``text`` without Coffer's managed block (unchanged when there is none)."""
    return _BLOCK_RE.sub("\n", text).lstrip("\n") if BLOCK_START in text else text


def _is_block_list(text: str) -> bool:
    """Whether the remaining document is empty, an empty flow list, or a block
    list a further ``- `` item can be appended to."""
    meaningful = [
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    if not meaningful:
        return True
    if len(meaningful) == 1 and meaningful[0].strip() == "[]":
        return True
    return meaningful[0].startswith("- ") or meaningful[0] == "-"


def apply_install(text: str, command: str, args: Sequence[str]) -> str:
    """``text`` with Coffer's block replaced, or appended when absent.

    Raises ``ConfigFileFormatInvalid`` when the file does not parse, or is not a
    block-style list Coffer can append one item to — then the person has to
    add the row themselves (the error says what it is)."""
    load_patches(text)
    rest = strip_block(text)
    if not _is_block_list(rest):
        raise ConfigFileFormatInvalid(
            "yaml", "Coffer can only add its row to a block-style list of patches"
        )
    meaningful = [ln for ln in rest.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if len(meaningful) == 1 and meaningful[0].strip() == "[]":
        rest = "\n".join(ln for ln in rest.splitlines() if ln.strip() != "[]")
    body = rest.rstrip("\n")
    block = render_block(command, args)
    new_text = f"{body}\n\n{block}" if body.strip() else block
    load_patches(new_text)  # the result must still parse
    return new_text


def apply_uninstall(text: str) -> str:
    """``text`` without Coffer's block (a no-op when there is none)."""
    return strip_block(text)
