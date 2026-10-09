"""The two native-memory writers: Claude Code, Codex.

See spec memory "Write the hub into Claude Code's native memory" and "Write
the hub into Codex's memory extension". Two writers written as two, on
purpose: a third agent earns an abstraction over them, and not before (see
"Reintroduce no retired memory mechanism")."""

from __future__ import annotations

from coffer.infrastructure.memory.writers.claude_code import ClaudeCodeMemoryWriter
from coffer.infrastructure.memory.writers.codex import CodexMemoryWriter

MEMORY_WRITERS = (ClaudeCodeMemoryWriter(), CodexMemoryWriter())

__all__ = ["MEMORY_WRITERS", "ClaudeCodeMemoryWriter", "CodexMemoryWriter"]
