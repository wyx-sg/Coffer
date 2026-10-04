"""The naming rule for a resource's own secret (spec secret "Name a resource's
secret after the resource and its slot")."""

from __future__ import annotations

import pytest

from coffer.domain.secrets import is_named_for, ref_segment, resource_secret_ref, slot_of


@pytest.mark.parametrize(
    ("name", "segment"),
    [
        ("confluence", "confluence"),
        ("my bot", "my-bot"),
        ("a/b", "a-b"),
        ("Agnes_Hub.v2-x", "Agnes_Hub.v2-x"),
        ("ünï", "-n-"),
        (".hidden", "hidden"),
        ("..", "x"),
        ("", "x"),
    ],
)
def test_ref_segment(name: str, segment: str) -> None:
    assert ref_segment(name) == segment


def test_resource_secret_ref() -> None:
    assert resource_secret_ref("provider", "agnes hub", "key") == "provider/agnes-hub/key"
    assert (
        resource_secret_ref("mcp_server", "confluence", "CONFLUENCE_PERSONAL_TOKEN")
        == "mcp_server/confluence/CONFLUENCE_PERSONAL_TOKEN"
    )


def test_is_named_for_accepts_a_collision_suffix_only() -> None:
    assert is_named_for("provider/agnes/key", "provider", "agnes", "key")
    assert is_named_for("provider/agnes-2/key", "provider", "agnes", "key")
    assert is_named_for("provider/agnes-17/key", "provider", "agnes", "key")
    assert not is_named_for("provider/agnes-1/key", "provider", "agnes", "key")
    assert not is_named_for("provider/agnes-x/key", "provider", "agnes", "key")
    assert not is_named_for("provider/agnes/token", "provider", "agnes", "key")
    assert not is_named_for("channel/agnes/key", "provider", "agnes", "key")
    assert not is_named_for("provider/643784232a6652abbf02c0f6aaf4a904/key", "provider", "a", "key")


def test_slots() -> None:
    assert slot_of("mcp_server", "JIRA_TOKEN") == "JIRA_TOKEN"
    assert slot_of("channel", "bot_token_ref") == "bot-token"
    assert slot_of("channel", "app_secret_ref") == "app-secret"
    assert slot_of("channel", "default_agent") is None
    assert slot_of("provider", "secret_ref") == "key"
    assert slot_of("skill", "x") is None
