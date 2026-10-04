"""The two `MemoryReader` adapters: Claude Code, Codex.

See spec memory "Read Claude Code and Codex memory with their search terms".

Each turns one agent's native memory files into `RawEntry`s — the hidden `.raw/`
input layer the distil pass reads, not notes anyone will be shown (see "Keep raw
entries verbatim and hidden", "Distil each raw entry into a note mechanically"). Two readers
written as two readers, on purpose: a third agent earns an abstraction over
them, and not before (see "Reintroduce no retired mechanism").

Each declares the agent it reads (``agent_type``); the composition root binds
them to the agents' memory-reader facets (ADR
agent-mechanisms-are-optional-facets-on-the-descriptor)."""

from __future__ import annotations

from coffer.infrastructure.memory.readers.claude_code import ClaudeCodeMemoryReader
from coffer.infrastructure.memory.readers.codex import CodexMemoryReader

MEMORY_READERS = (ClaudeCodeMemoryReader(), CodexMemoryReader())

__all__ = ["MEMORY_READERS", "ClaudeCodeMemoryReader", "CodexMemoryReader"]
