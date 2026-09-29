"""A group thread inherits the group's settings, but not another agent's model
(spec channels "Keep a chat's settings across its conversations")."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.channel.conversation_ops import inherited_setting
from coffer.application.channel.store_ports import ChannelThreadConversation


def _row(thread: str, **fields: str | None) -> ChannelThreadConversation:
    return ChannelThreadConversation(
        resource_id=1,
        chat_id="g",
        thread_id=thread,
        active_conversation_id=None,
        preferred_agent=fields.pop("agent", None),
        updated_at=datetime.now(tz=UTC),
        **fields,  # type: ignore[arg-type]
    )


GROUP = _row("", agent="codex", preferred_model="gpt-5", preferred_cwd="/w")


@pytest.mark.acceptance(spec="channels", scenario="a group thread inherits the group's defaults")
def test_a_fresh_thread_takes_every_group_setting() -> None:
    thread = _row("t1")
    assert inherited_setting(thread, GROUP, "preferred_agent") == "codex"
    assert inherited_setting(thread, GROUP, "preferred_model") == "gpt-5"
    assert inherited_setting(None, GROUP, "preferred_cwd") == "/w"


def test_a_thread_on_another_agent_keeps_the_directory_but_not_the_model() -> None:
    thread = _row("t1", agent="claude_code")
    assert inherited_setting(thread, GROUP, "preferred_model") is None
    assert inherited_setting(thread, GROUP, "preferred_cwd") == "/w"


def test_a_thread_setting_wins() -> None:
    thread = _row("t1", preferred_model="opus")
    assert inherited_setting(thread, GROUP, "preferred_model") == "opus"
