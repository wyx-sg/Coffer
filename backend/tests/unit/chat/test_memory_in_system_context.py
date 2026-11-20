"""Coffer's own turns carry the project's memories in the system prompt (spec
memory "Hand a session its project's memories at start")."""

from __future__ import annotations

import pytest

from coffer.infrastructure.chat.adapter_support import compose_system_context


@pytest.mark.acceptance(
    spec="memory", scenario="a conversation in Coffer carries the memories in its system prompt"
)
async def test_the_memories_come_first_in_the_system_context() -> None:
    memory = '<coffer-memory project="p">\nNever mock the vault.\n</coffer-memory>\n'
    text = await compose_system_context(
        agent_key="claude_code", channel_uid="", model=None, list_models=None, memory=memory
    )
    assert text.startswith(memory.rstrip("\n"))
    bare = await compose_system_context(
        agent_key="claude_code", channel_uid="", model=None, list_models=None
    )
    assert "coffer-memory" not in bare
