"""The two ``MemoryReader`` adapters: Claude Code, Codex (spec memory "Read
Claude Code and Codex memory").

Each turns one agent's native memory files into ``RawEntry`` values and
declares the agent it reads (``agent_type``); the composition root binds them
to the agents' memory-reader facets (ADR
agent-mechanisms-are-optional-facets-on-the-descriptor)."""

from __future__ import annotations

from coffer.infrastructure.memory.readers.claude_code import ClaudeCodeMemoryReader
from coffer.infrastructure.memory.readers.codex import CodexMemoryReader

MEMORY_READERS = (ClaudeCodeMemoryReader(), CodexMemoryReader())

__all__ = ["MEMORY_READERS", "ClaudeCodeMemoryReader", "CodexMemoryReader"]
