"""The import preview's pure text rules: redacted unified-diff hunks and server names."""

from __future__ import annotations

import json

from coffer.domain.agent.config_diff import (
    REDACTED,
    diff_hunks,
    entry_secret_literals,
    normalise_server_name,
    redact_line,
    server_name_usable,
)
from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_entries import McpEntry, parse_entries, remove_entry


def test_redact_line_hides_secret_looking_keys_in_json_and_toml() -> None:
    assert redact_line('  "GITHUB_TOKEN": "ghp_abc123",', []) == f'  "GITHUB_TOKEN": "{REDACTED}",'
    assert redact_line('env = { API_KEY = "xyz12345", LOG = "debug" }', []) == (
        f'env = {{ API_KEY = "{REDACTED}", LOG = "debug" }}'
    )
    assert redact_line("bearer_token = 'tt1234'", []) == f"bearer_token = '{REDACTED}'"
    assert redact_line('  "Authorization": "Bearer abc"', []) == f'  "Authorization": "{REDACTED}"'


def test_redact_line_keeps_plain_values_and_empty_secrets() -> None:
    assert redact_line('  "command": "uvx",', []) == '  "command": "uvx",'
    assert redact_line('  "primaryApiKey": "",', []) == '  "primaryApiKey": "",'


def test_redact_line_replaces_known_literals_anywhere() -> None:
    assert redact_line('      "sekret-literal"', ["sekret-literal"]) == f'      "{REDACTED}"'
    # Too short to replace inside other text.
    assert redact_line("on and on", ["on"]) == "on and on"


def test_redact_line_cuts_long_lines() -> None:
    assert len(redact_line("x" * 5000, [])) == 400


def test_entry_secret_literals_reads_env_headers_flags_and_extra() -> None:
    entry = McpEntry(
        name="gh",
        source="global",
        transport="stdio",
        command="npx",
        args=("--token", "flag-secret", "--api-key=eq-secret", "--verbose", "x"),
        env={"GITHUB_TOKEN": "env-secret", "LOG": "debug"},
        extra={"bearer_token": "extra-secret"},
    )
    assert sorted(entry_secret_literals([entry])) == sorted(
        ["env-secret", "flag-secret", "eq-secret", "extra-secret"]
    )


def test_diff_hunks_of_a_removed_entry_are_redacted_everywhere() -> None:
    before = json.dumps(
        {
            "mcpServers": {
                "a": {"command": "a-cmd", "env": {"A_TOKEN": "tok-aaaa"}},
                "b": {"command": "b-cmd", "env": {"B_TOKEN": "tok-bbbb"}},
            }
        },
        indent=2,
    )
    after = remove_entry(ConfigFileFormat.JSON, before, "a")
    literals = entry_secret_literals(parse_entries(ConfigFileFormat.JSON, before, source="global"))
    hunks, added, removed = diff_hunks(before, after, literals=literals, section="mcpServers")
    assert removed >= 5
    assert added == 0
    (hunk,) = hunks
    assert hunk.header.startswith("@@ -1,11 +1,5 @@")
    assert hunk.header.endswith("@@ mcpServers")
    text = "\n".join(line.text for line in hunk.lines)
    assert "tok-aaaa" not in text
    assert "tok-bbbb" not in text
    assert any(line.kind == "remove" and "a-cmd" in line.text for line in hunk.lines)
    removed_lines = [line for line in hunk.lines if line.kind == "remove"]
    assert all(line.new_line is None and line.old_line for line in removed_lines)


def test_diff_hunks_carry_old_and_new_line_numbers() -> None:
    before = "\n".join("abcdefghi")
    after = "\n".join("abcdfghi")
    (hunk,), added, removed = diff_hunks(before, after, section="s")
    assert (hunk.old_start, hunk.old_count, hunk.new_start, hunk.new_count) == (2, 7, 2, 6)
    assert (added, removed) == (0, 1)
    assert [(ln.kind, ln.old_line, ln.new_line) for ln in hunk.lines][3:5] == [
        ("remove", 5, None),
        ("context", 6, 5),
    ]


def test_no_change_has_no_hunks() -> None:
    assert diff_hunks("a\nb\n", "a\nb\n") == ((), 0, 0)


def test_normalise_server_name_follows_the_registration_rule() -> None:
    assert normalise_server_name("My Server__X") == "my-server_x"
    assert normalise_server_name("@@") == "server"
    assert normalise_server_name("GitHub") == "github"


def test_server_name_usable() -> None:
    assert server_name_usable("github")
    assert not server_name_usable("a__b")
    assert not server_name_usable("x" * 25)
    assert not server_name_usable("has space")
