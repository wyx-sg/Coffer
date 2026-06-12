"""Agent-side memory projection (spec 007).

Adapters + engine that project the canonical memory store into each agent's
native location. Lives in the agent layer so the memory substrate stays
agent-agnostic (FR-014); nothing here imports the memory kind (Contract 5b).
"""

from coffer.application.agent.projection.adapters import (
    AgentMemoryAdapter,
    ClaudeCodeMemoryAdapter,
    CodexMemoryAdapter,
    claude_project_slug,
)
from coffer.application.agent.projection.engine import ProjectionEngine, default_adapters
from coffer.application.agent.projection.types import (
    MANAGED_BLOCK_END,
    MANAGED_BLOCK_START,
    CanonicalMemory,
    MemoryLayer,
    ProjectionFs,
    ProjectionMode,
    ProjectionResult,
    SymlinkOutcome,
)

__all__ = [
    "MANAGED_BLOCK_END",
    "MANAGED_BLOCK_START",
    "AgentMemoryAdapter",
    "CanonicalMemory",
    "ClaudeCodeMemoryAdapter",
    "CodexMemoryAdapter",
    "MemoryLayer",
    "ProjectionEngine",
    "ProjectionFs",
    "ProjectionMode",
    "ProjectionResult",
    "SymlinkOutcome",
    "claude_project_slug",
    "default_adapters",
]
