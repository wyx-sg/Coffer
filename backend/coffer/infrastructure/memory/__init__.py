"""Memory infrastructure: the memory files on disk, read and written.

The readers are read-only: they list and parse what Claude Code and Codex
already keep in their own memory files (spec memory FR-001/FR-002) and never
write there. Alongside them sits the vault's own fact store — ``store.py`` and
``source_state.py`` write the derived tree under `~/.coffer/memory/`, which the
aggregation pass in `coffer.application` drives.
"""
