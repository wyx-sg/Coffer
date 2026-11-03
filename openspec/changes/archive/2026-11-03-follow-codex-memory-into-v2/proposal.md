## Why

Codex Desktop 0.163 and later keeps its memory in `~/.codex/memories_v2/` beside the v1 folder `~/.codex/memories/`, and picks one per thread from a server-side switch (it passes `-c memories.version=…` to its app server; `config.toml` says nothing). Coffer wrote only into `memories/extensions/coffer/` and read only `memories/`, so a v2 thread never saw what Claude Code learned, and what Codex learned in v2 never reached the hub. On the owner's Mac (2026-11-03) both folders were being updated (Codex dual-writes), v1 held 70 Coffer resources and v2 none.

## What Changes

- The Codex writer writes the same `extensions/coffer/` into every Codex memory folder that is there (`memories/`, `memories_v2/`), as Codex's own import from Claude Code does. Each folder is its own write location with its own ledger key, status and copy counts.
- A `memories_v<N>` folder newer than any Coffer knows is listed as a location that writes nothing and is reported as unrecognised, so the Memory page says Codex moved on.
- The Codex reader also reads `memories_v2/memory_summary.md`: its profile, preferences, each General Tips paragraph and each What's in Memory topic. A topic is filed under the `cwd:` in the header of the rollout summary it points at; nothing below that header is read. While a v2 summary is there, the profile comes from it and v1's summary yields only the preferences v2 does not state word for word.
- The checkout map and the agent page's native-memory listing read v2's recorded directories too.
- The Memory page API gives each agent a `locations` list; the agent's Memory tab shows Codex's copies per folder.

## Impact

- Specs: memory (Read no transcripts or rollouts; Write the hub into Codex's memory extension; new: Read Codex's v2 memory).
- Code: `backend/coffer/infrastructure/memory/writers/codex.py`, `readers/codex.py`, `codex_identity.py`, `checkouts.py`, `infrastructure/agent_files/codex_rollout_summaries.py`, `infrastructure/agent/codex_memory_store.py`, `domain/agent/codex_memory.py`, `domain/agent/native_memory.py`, `domain/memory/native_writer.py`, `application/memory/sync_*.py`, `surfaces/http/memory/sync_routes.py`; `frontend/src/components/agents/AgentMemorySync.tsx`.
- ADR: `follow-codex-memory-into-every-version-folder`.
- Docs: memory guide and architecture (English and Chinese).
