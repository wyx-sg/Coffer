"""The two `MemoryReader` adapters (spec memory FR-004): Claude Code, Codex."""

from __future__ import annotations

from coffer.infrastructure.memory.readers.claude_code import ClaudeCodeMemoryReader
from coffer.infrastructure.memory.readers.codex import CodexMemoryReader

__all__ = ["ClaudeCodeMemoryReader", "CodexMemoryReader"]
