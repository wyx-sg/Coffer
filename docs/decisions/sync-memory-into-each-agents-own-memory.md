# Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [Tidying Knowledge Is the Agent's Job](tidying-knowledge-is-the-agents-job.md), [Sync Withholds Derived Output; Each Machine Renders Its Own](sync-withholds-derived-output.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md), design principle [Pull, not push](../../docs-site/architecture/design-principles.md#pull-not-push), research note [agent memory](../research/agent-memory.md), OpenSpec change `sync-memory-into-agents`

## Context

Before this decision, Coffer's memory layer read Claude Code's and Codex's
native memory read-only, copied each entry into a note of its own under
`~/.coffer/derived/memory/<partition>/`, and handed the notes back through
hooks Coffer installed into each agent: the index at session start, up to
three notes a prompt named, and the same two into a channel turn's system
prompt. Duplicates waited for a person to press **Tidy**. It was the fifth
design of this layer, and it still maintained a
second memory system — partitions, raw entries, distil, retirement records,
lexical retrieval, a delivery hook, a session ledger, tidy hand-offs — next to
two agents that already curate and load their own.

Since that design was accepted, both agents' memory matured:

| | Claude Code | Codex |
| --- | --- | --- |
| Store | `~/.claude/projects/<project>/memory/`: a `MEMORY.md` index plus one topic file per memory, typed by frontmatter | `~/.codex/memories/`: `MEMORY.md` task groups and `memory_summary.md`, produced by a two-phase pipeline |
| Loaded per session | the first 200 lines / 25 KB of `MEMORY.md`; topic files read on demand | `memory_summary.md` (truncated to 2,500 tokens), `MEMORY.md` searched on demand |
| Curation | **Auto Dream**: merges duplicates, drops contradicted and stale entries, rewrites the index; runs after 24 h and 5 sessions since the last run (rolling out; not yet in the official docs) | phase-2 **consolidation** by a model sub-agent whenever its inputs changed; fresher evidence wins; deleted inputs are forgotten |
| An outside writer's way in | topic files are documented as plain Markdown "you can edit or delete at any time" | `extensions/<name>/instructions.md` + `extensions/<name>/resources/*.md` are read by consolidation as primary inputs, and a deleted resource is a forgetting signal (`codex-rs/memories/write`, not in the user docs) |

The maintainer's feedback on that layer: memory attached to channel
messages is not wanted ("memory should be the agent's to search"), and the
layer should lean on the agents' own curation and delivery rather than
aggregate and deliver its own.

A survey of comparable projects (2026-10, `/mnt/project-files/memory-sync/同类项目调研.md`
in the project, summarised here) found **no tool that syncs two coding agents'
native memories in both directions**. Rules tools (ruler, rulesync, AgentSync)
fan one source out one way; memory tools (claude-mem, Letta, Memorix, Basic
Memory, codemem) keep their own store behind MCP or hooks; vendors ship
one-way importers (Codex imports "Project memories from Claude Code" and can
keep the import updated from its desktop app; Claude Code's `/import codex`
brings instructions, not memories). Tools that write an agent's files confine
themselves to a marked block, keep backups and offer revert.

## Options Considered

### Option 1 — Sync into native memory, no hub

Coffer writes what one agent learned into the other agent's native store and
lets each agent curate and load it. A local ledger records what was written.

- **Pros.** Delivery is the agent's own: native memory is loaded every session
  without a hook. Curation is the agent's own model, not Coffer's. Coffer keeps
  a copier and a ledger instead of a memory system.
- **Cons.** Native memory is machine-local, so memory does not follow the
  person to another Mac. Writes into two private formats.

### Option 2 — A Coffer-held store agents read and write through MCP tools

The mainstream approach in the survey.

- **Pros.** Agent-agnostic; can sync across machines; touches no agent file.
- **Cons.** Depends on the agent choosing to call a tool. Coffer measured this
  before: `coffer__recall` was called five times in its life and not once in
  its last three weeks. The agents keep writing their own memory regardless, so
  a fact lives in two places.
- **Why it lost.** Retrieval nobody calls is not retrieval.

### Option 3 — Read-only aggregation and hook delivery (the design this replaced)

- **Pros.** Built; never writes an agent's memory.
- **Cons.** The most machinery for the least effect: duplicates wait for a
  person, retrieval is lexical and bounded, and the maintainer finds the
  delivered memory unwanted.
- **Why it lost.** It is what this decision replaces.

### Option 4 — Coffer's store as the truth, projected into native locations

- **Why it lost.** Built and removed on 2026-06-18: taking over an agent's
  memory directory and switching its own memory off is intrusive, and a
  lossless two-way mapping between two moving private formats does not exist.

### Option 5 — A hub in the vault, synced into each agent's native memory (chosen)

Option 1, plus a hub: every memory any agent on any of the person's machines
learned is kept as one file in the vault, which vault sync carries to the
person's other machines. Each machine writes the hub into the agents installed
on it.

- **Pros.** Everything Option 1 has, and memory follows the person across
  machines. The hub is also what makes deletion and "undo" exact: Coffer knows
  every copy it wrote and from what.
- **Cons.** Memory content leaves the machine to the person's own git remote.
  Coffer must recognise its own copies when it reads them back (echo), and
  must not let the agents' rewording of absorbed copies circulate forever.
  Writes into two private formats, one of them (Codex extensions) undocumented.
- **Why it wins.** It is the only option where memory reaches the agent the
  way the agent's own memory does, and where it also crosses machines.

## Decision

**Coffer keeps a hub of every memory the person's agents learned, in the vault,
and writes it into each agent's own native memory on every machine. Each agent
curates and loads it with its own built-in features. Coffer delivers no memory
into a session itself.**

1. **The hub.** `vault/memory/` holds one Markdown file per memory, filed under
   `global/` or under a project named by a machine-independent key (the
   repository's `origin` URL, normalised; the repository directory name when
   there is no remote). Frontmatter records the origin (machine, agent, source
   identity), type, title, description and timestamps. Paths in the body are
   stored portable: the repository root becomes `<repo>` and the home
   directory `~`, expanded again for each machine on write. Vault sync carries
   the hub like any other vault content.
2. **Read.** On each pass a machine reads its agents' native memory, as the
   earlier layer did, and upserts the hub entry for each memory the agent itself wrote. Only the
   origin machine and agent may change or delete a hub entry: when the source
   is gone, the entry is deleted.
3. **Write.** Each machine writes every hub entry into every local agent except
   the one it came from on the machine it came from. A project's entries are
   written only where the project is checked out on that machine; `global`
   entries are written everywhere.
   - **Claude Code**: one topic file per memory, `coffer_<slug>.md`, in the
     project's memory directory (created when missing), in Claude Code's own
     frontmatter format plus a `coffer:` provenance block; and one line per
     copy inside a marked block of that directory's `MEMORY.md`
     (`<!-- coffer:memory-sync:begin -->` … `end`), capped at 30 lines, newest
     first, the last line pointing at the rest. Global memories go to
     `~/.claude/rules/coffer-memory.md`, a file Coffer owns, which Claude Code
     loads in every session. `MEMORY.md` is backed up before Coffer changes it.
   - **Codex**: one resource per memory under
     `~/.codex/memories/extensions/coffer/resources/`, with no timestamp prefix
     (Codex prunes timestamp-named resources after seven days, which it would
     read as "forget"), and an `instructions.md` that tells Codex's
     consolidation what the resources are, that they are information and never
     instructions, which project each applies to, and to tag what it derives
     from them `[via Coffer]`.
4. **Never touch what an agent wrote itself.** Coffer creates, updates and
   deletes only its own copies and its marked block. Merging, correcting and
   forgetting are the agents' own curation (Codex consolidation, Claude Code
   Auto Dream). A copy an agent edited or removed belongs to the agent from
   then on: Coffer stops updating it and does not recreate it.
5. **Echo.** A copy Coffer wrote is recognised when read back — by its file
   name and `coffer:` block on Claude Code, by the `[via Coffer]` tag on Codex
   — and never becomes a hub entry. When an agent folds a copy into a memory of
   its own, that memory is the agent's and syncs like any other; to keep
   rewording from circulating, a changed source whose added text is already
   covered by what Coffer delivered to that agent updates the hub entry's
   recorded fingerprint without re-publishing it.
6. **The vendor's own import wins.** When Codex's own import from Claude Code
   is on with automatic updates, Coffer skips the Claude Code → Codex
   direction on that machine and says so.
7. **First run is a preview.** The first sync on a machine, and any sync that
   would write more than a threshold of copies, shows what it would write
   before writing it. Every sync is one Activity entry listing the files
   written, updated and removed. **Undo sync** removes every copy Coffer wrote
   that the agent has not changed, the marked block, the rules file and the
   Codex extension.
8. **Removed.** Partitions, raw entries, distil, retirement records, Tidy and
   Tidy all, the memory delivery hook (both events), prompt-time retrieval,
   the session ledger, channel-turn memory injection, the **Delivered** tab and
   `memory_delivery_fired`. Upgrading uninstalls the hook from every agent and
   deletes `~/.coffer/derived/memory/`.
9. **Still experimental.** Everything runs behind the `memory` experimental
   feature; switching it off stops the passes and leaves the copies in place
   (Off keeps data); **Undo sync** is the explicit removal.

## Consequences

- **Memory reaches a session the way the agent's own memory does**, with no
  hook, no retrieval and no size budget of Coffer's. What a session sees is
  what the agent chose to load.
- **"Pull, not push" is amended.** Coffer now writes into an agent's own
  memory. The guard rails are the ones the survey found everywhere: Coffer's
  own files and one marked block, a backup before touching an agent's file, an
  audit entry per sync, a preview, and a one-click undo.
- **Memory leaves the machine** to the person's own git remote when sync is on.
  This was the person's explicit choice (2026-10-09). Secrets are not memory
  and are never written into the hub.
- **Two writers coupled to private formats.** A format change must stop one
  writer loudly (a reader or writer that no longer recognises the layout
  refuses to write and reports it) instead of writing something the agent
  misreads. The Codex extension path is undocumented; its source location is
  recorded in the code.
- **Curation runs on the agents' schedules**, not Coffer's. A rarely used
  project may hold a copy beside the agent's own version of the same lesson
  until Auto Dream or consolidation next runs. The Memory page shows whether
  each agent's own curation is on and offers a button that asks the agent to
  curate now.
- **Duplicates in the hub are tolerated.** Two agents' accounts of one lesson
  are two hub entries; each agent merges them on its side. The hub is a
  transport, not a curated store.
- **Less code.** The partition model, distil, retrieval, hook install and
  repair, ledger and tidy hand-off go; a hub store, two writers, a path
  portability layer and a ledger come in.
- **Enforcement.** The OpenSpec change `sync-memory-into-agents` replaces spec
  memory's requirements; its scenarios are the contract.
