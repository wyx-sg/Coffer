"""The two `MemoryReader` adapters: Claude Code, Codex.

See spec memory "Read Claude Code and Codex memory with their search terms".

Each turns one agent's native memory files into `RawEntry`s — the hidden `.raw/`
input layer the distil pass reads, not notes anyone will be shown (see "Keep raw
entries verbatim and hidden", "Write notes in Coffer's own words"). Two readers
written as two readers, on purpose: a third agent earns an abstraction over
them, and not before (see "Reintroduce no retired mechanism")."""

from __future__ import annotations

from coffer.infrastructure.memory.readers.claude_code import ClaudeCodeMemoryReader
from coffer.infrastructure.memory.readers.codex import CodexMemoryReader

__all__ = ["ClaudeCodeMemoryReader", "CodexMemoryReader"]
