"""Application services for the `memory` resource kind."""

from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.service import MemoryService

__all__ = ["MemoryService", "make_memory_kind"]
