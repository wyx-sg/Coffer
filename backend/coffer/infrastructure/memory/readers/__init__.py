"""The two `MemoryReader` adapters (spec memory FR-004): Claude Code, Codex.

Each turns one agent's native memory files into `RawEntry`s — the hidden
`.raw/` input layer the distil pass reads, not notes anyone will be shown
(FR-008, FR-020). Two readers written as two readers, on purpose: a third
agent earns an abstraction over them, and not before (FR-045)."""

from __future__ import annotations

from coffer.infrastructure.memory.readers.claude_code import ClaudeCodeMemoryReader
from coffer.infrastructure.memory.readers.codex import CodexMemoryReader

__all__ = ["ClaudeCodeMemoryReader", "CodexMemoryReader"]
