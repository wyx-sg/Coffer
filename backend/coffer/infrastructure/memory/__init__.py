"""Memory infrastructure: read-only adapters over agents' own memory.

Nothing here writes a file. It only lists and parses what Claude Code and
Codex already keep on disk (spec memory FR-001/FR-002); the aggregation pass
that turns that into `~/.coffer/memory/` lives in `coffer.application`.
"""
