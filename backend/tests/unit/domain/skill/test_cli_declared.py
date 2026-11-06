"""A hand-added tool's stored shape."""

from __future__ import annotations

from coffer.domain.skill.cli_declared import DeclaredTool, from_document, to_document


def test_a_login_check_an_older_build_stored_is_not_read_or_written_back() -> None:
    stored = {"command": "jq", "title": "JSON", "login_check": ["jq", "auth", "status"]}
    tool = from_document(stored)
    assert tool == DeclaredTool("jq", "JSON")
    assert "login_check" not in to_document(tool)
