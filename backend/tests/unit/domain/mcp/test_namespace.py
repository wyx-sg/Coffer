# backend/tests/unit/domain/mcp/test_namespace.py
import pytest

from coffer.domain.errors import InvalidPrefix
from coffer.domain.mcp.namespace import (
    parse_prefixed_prompt,
    parse_prefixed_tool,
    parse_prefixed_uri,
    prefix_prompt,
    prefix_resource_uri,
    prefix_tool,
)


def test_prefix_tool_round_trip():
    assert prefix_tool("filesystem", "read_file") == "filesystem__read_file"
    assert parse_prefixed_tool("filesystem__read_file") == ("filesystem", "read_file")


def test_prefix_prompt_round_trip():
    assert prefix_prompt("github", "summarize_pr") == "github__summarize_pr"
    assert parse_prefixed_prompt("github__summarize_pr") == ("github", "summarize_pr")


def test_prefix_resource_uri_round_trip():
    assert (
        prefix_resource_uri("filesystem", "file:///tmp/x.txt")
        == "coffer://filesystem/file:///tmp/x.txt"
    )
    assert parse_prefixed_uri("coffer://filesystem/file:///tmp/x.txt") == (
        "filesystem",
        "file:///tmp/x.txt",
    )


@pytest.mark.parametrize(
    "bad",
    ["no_separator", "__missing_server", "filesystem__", ""],
)
def test_parse_prefixed_tool_rejects_malformed(bad):
    with pytest.raises(InvalidPrefix):
        parse_prefixed_tool(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "file:///not-prefixed",
        "coffer://",
        "coffer:///no_server",
        "coffer://server/",
    ],
)
def test_parse_prefixed_uri_rejects_malformed(bad):
    with pytest.raises(InvalidPrefix):
        parse_prefixed_uri(bad)


def test_tool_name_with_internal_underscores_preserved():
    """Tools whose own names contain underscores still round-trip."""
    assert prefix_tool("fs", "deeply_nested_call") == "fs__deeply_nested_call"
    assert parse_prefixed_tool("fs__deeply_nested_call") == ("fs", "deeply_nested_call")


def test_resource_uri_with_query_string():
    uri = "https://api.example.com/v1/things?id=42"
    prefixed = prefix_resource_uri("github", uri)
    assert parse_prefixed_uri(prefixed) == ("github", uri)
