## Why

Coffer's memory layer keeps a second memory system beside two agents that
already curate and load their own: it copies every Claude Code and Codex memory
into notes of its own, waits for a person to press Tidy to merge duplicates,
and hands notes back through a hook at session start, at every prompt and in
every channel turn. The maintainer does not want memory attached to messages,
and wants the layer to lean on the agents' own curation and delivery instead.
Both agents now curate their own memory (Codex consolidation, Claude Code Auto
Dream) and load it every session. What neither can do is see what the other
learned, or what it learned on the person's other machine.

The decision and the options weighed are in
[Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](../../../docs/decisions/sync-memory-into-each-agents-own-memory.md).

## What Changes

- memory: **BREAKING** the layer becomes a sync. Each machine reads its agents'
  native memory and publishes every memory an agent wrote itself into a hub,
  `vault/memory/`, one file per memory, filed under `global` or a
  machine-independent project key, with paths stored as `<repo>` and `~`.
  Vault sync carries the hub between the person's machines.
- memory: each machine writes every hub entry into every local agent except the
  one it came from: Claude Code gets `coffer_<slug>.md` topic files plus a
  marked, capped block in the project's `MEMORY.md`, and global memories in
  `~/.claude/rules/coffer-memory.md`; Codex gets resources in its memory
  extension folder `memories/extensions/coffer/` with an `instructions.md`.
  A project is written only where it is checked out.
- memory: Coffer never changes a memory an agent wrote itself; a copy the agent
  edited or removed is left to the agent. Copies are recognised when read back
  and never republished, and an agent's rewording of what it absorbed does not
  circulate. A memory that looks like a secret is withheld.
- memory: when Codex's own import from Claude Code is on with automatic
  updates, Coffer leaves that direction to Codex.
- memory: the first sync on a machine, and a large one, waits for the person
  to confirm a preview. Every sync is one `memory_synced` Activity entry.
  **Undo sync…** removes every unedited copy and Coffer's block, rules file and
  extension folder.
- memory: the Memory page shows the sync, the hub's projects and where each
  memory was written, and each agent's own curation state with **Curate now**.
- memory: **BREAKING** removed: partitions, raw entries, distil, retirement
  records, Tidy and Tidy all, notes editing and deletion, the Delivered tab,
  the memory delivery hook, prompt-time retrieval, the session ledger,
  channel-turn memory injection, `memory_delivery_fired`, the `coffer memory`
  commands that served them and their REST routes. Upgrading removes the hook
  from every agent and deletes `~/.coffer/derived/memory/`.
- resource-framework: **BREAKING** `memory` is no longer a resource kind.
- vault-storage, vault-sync: `vault/memory/` is vault content and syncs; the
  derived memory tree is gone.
- experimental-features: the `memory` feature gates the sync worker and the
  Memory page; switching it off stops syncing and leaves copies in place.
- agent-registry (+ claude-code, codex): the agent's Coffer connection loses its
  `memory_hook` part; each child spec states where Coffer writes into that
  agent's memory and how its own curation state is read.
- channels, chat: a turn carries no memory from Coffer.
- internal-engine: the aggregate and distil switches and intervals become one
  memory sync switch and interval.
- web-ui: the Memory page and its routes change as above.

## Capabilities

### Modified Capabilities

- `memory`
- `resource-framework`
- `vault-storage`
- `vault-sync`
- `experimental-features`
- `agent-registry` (`claude-code`, `codex`)
- `channels`
- `chat`
- `internal-engine`
- `web-ui`

## Impact

- Backend: `application/memory/`, `infrastructure/memory/`, `domain/memory/`,
  the memory routes and CLI, chat prompt composition, agent hook
  installation, the kind registry, a start-up migration.
- Frontend: the Memory pages and the agent Hooks tab.
- Docs: memory guide and architecture pages (en + zh), filesystem, CLI and
  REST references, ADRs.
- Design canvas: Context canvas (Memory boards) and the Agents canvas (Hooks
  tab).
