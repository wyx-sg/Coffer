"""Infrastructure for the shared knowledge substrate (KB + memory).

The only layer that imports external engines (markitdown, sqlite-vec, openai,
fastembed) and the ripgrep binary. Importing this package registers the unified
``documents`` / ``chunks`` ORM models on ``Base.metadata``.
"""

from coffer.infrastructure.knowledge import (
    ddl,
    models,
)

__all__ = ["ddl", "models"]
