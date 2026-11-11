---
title: Memory
description: How Coffer keeps a hub of every agent's memories in the vault, writes them into each agent's own memory as that agent loads it, syncs only memories learned in a repository, and leaves curation to the agents.
---

# Memory

This page explains how Coffer's memory layer works: how it reads what Claude Code and Codex have learned out of their own memory files, keeps every memory in a hub in the vault, and writes each one into the other agents' own memory on every machine. It is written for engineers who want the mechanism and the reasoning behind it. For the task-oriented view, see the [Memory guide](/guides/memory).

## The problem

Every coding agent keeps its own memory, and none of them can see another's. Claude Code writes one Markdown file per memory under each project and loads its `MEMORY.md` index every session. Codex distils its rollouts into task groups and a profile and loads its summary every session. Both now curate their own memory too: Claude Code's Auto Dream merges and prunes, Codex's consolidation rewrites its memory whenever its inputs change. What neither can do is see what the other learned, or what it learned on the person's other machine.

Coffer's answer is a sync, not a memory system of its own:

1. **Publish.** Each machine reads its agents' native memory and publishes every memory an agent wrote itself into a **hub**, `vault/memory/`, one file per memory. Vault sync carries the hub between the person's machines.
2. **Write.** Each machine writes every hub entry into every local agent except the one it came from, in that agent's own format, where the agent loads it as its own memory.
3. **Leave curation and loading to the agents.** Coffer delivers nothing into a session and never edits a memory an agent wrote. Merging, correcting and forgetting are each agent's own curation.

Memory is about the person; [knowledge](/architecture/knowledge) is about the world. Memory holds who the person is, how to work with them, and a project's current state; it reaches a session the way the agent's own memory does. Knowledge holds how outside systems, teams and processes work, with a source and a recheck date, and agents pull it on demand through the `coffer-guide` catalogue. A fixed sequence of steps is a skill. Agents still write task notes into their own memory; Coffer syncs them like any project memory and leaves moving one into knowledge to the person and their agent. Only memories learned in a repository are synced: what an agent learned outside any repository stays with it (see [Project memories only](#project-memories-only)). Writing into an agent's memory is a bounded exception to [pull, not push](/architecture/design-principles#pull-not-push): Coffer writes only files of its own and one marked block, backs up what it changes, shows a first or large sync as a preview, audits every sync and offers a one-click undo. The decision and the options weighed are in the ADR [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-memory-into-each-agents-own-memory.md).

## The hub

```text
~/.coffer/vault/memory/
└── projects/
    └── github.com-acme-payments/
        └── <id>.md
```

A `sorted/` folder an earlier build wrote is not read; a `global/` one is emptied as [Project memories only](#project-memories-only) describes.

- **Project key.** A project is named by its repository's `origin` URL, normalised: the scheme, credentials, port and a trailing `.git` dropped, the host lower-cased, the path's case kept (`git@host:owner/repo.git` and `https://host/owner/repo` give one key). A repository with no remote falls back to its directory's name, because a path is not portable. A main checkout, its worktrees and another clone with the same `origin`, on any machine, are one project. The folder name is the key with every character outside `[A-Za-z0-9._-]` turned into `-`; the key itself is in each entry's `project:` frontmatter, so the folder name never has to be decoded.
- **Filing.** A memory goes where its agent filed it, whatever its type: one learned in a repository goes to that project. A Codex task group's `applies_to` can name a scratch chat directory and, beside it, the repository worked on; every path in it is read, and the first inside a repository wins. A memory with no working directory inside a repository (Codex's profile and preferences, a task group naming none, a scratch folder) is not published. See [ADR: file a memory where its agent filed it](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/file-a-memory-where-its-agent-filed-it.md).
- **Entry id.** The first 16 hex characters of `sha256(machine_id, agent_type, source_identity)`. The source identity is the Claude Code memory file's path under the config directory, or the Codex file plus task group, section and the bullet's content hash. A re-read of an unchanged source maps to the same id, and Codex bullets moving, appearing or disappearing around a memory leave its id alone. A Codex bullet that is not in the hub takes over the identity of the most alike memory its section no longer holds, when the two are at least 0.6 alike, so a reworded bullet is an update, not a new entry; anything less alike is a new memory.
- **Frontmatter.** `id`, `origin` (`machine`, `agent`, `source`), `project`, `type` (`user`, `feedback`, `project` or `reference`), `title`, `description`, `search_terms` when the source states them, `created_at` and `updated_at`. The body is the memory's text.
- **Portable paths.** On publish, the repository root (and every worktree root the agent recorded) is replaced by `<repo>`, then the home directory by `~`, longest match first and on path boundaries only. On write, `<repo>` expands to the project's checkout on the writing machine and `~` to its home. Any other path is left as written.
- **One writer per entry.** Only the origin machine and agent create, change or delete an entry; a machine never deletes another machine's entries because its own agents lack them. So two machines never edit one file, and a vault-sync merge of the hub is always clean.
- **One commit per sync.** A sync's hub changes are one vault commit with writer `memory-sync`, through the vault's ordinary validated write path.
- **Secrets are withheld.** Before an entry is published its text runs through the same detector as the Secrets scan and the sync push check. A hit withholds the entry; the report names the agent and source, never the value. The sync push check stays as the second line.

Duplicates in the hub are tolerated: two agents' accounts of one lesson are two entries, and each agent merges them on its own side. The hub is a transport, not a curated store.

## Reading native memory

Each supported agent has one reader, and every reader follows the same two-step contract: **list the sources** (the agent's memory files, each hashed without parsing), then **read a source** (parse one file into entries: title, description, type, verbatim body, anchor, project root and optional search terms). Splitting the two steps lets a sync skip an unchanged file before paying to parse it. Coffer reads only agents that are **registered**, at paths derived from each agent's own config directory.

| | Claude Code | Codex |
| --- | --- | --- |
| Files read | `<config_dir>/projects/<slug>/memory/*.md` | `<config_dir>/memories/MEMORY.md` and `memory_summary.md`; v2: `<config_dir>/memories_v2/memory_summary.md` |
| One entry per | memory file | populated bullet section of a task group (`User preferences`, `Reusable knowledge`, `Failures and how to do differently`), plus the profile and profile preferences in the summary; in v2, also each `## General Tips` paragraph and each topic of `## What's in Memory` |
| Title and description | frontmatter `name` and `description` | derived from the bullet |
| Type | `metadata.type`: `user`, `feedback`, `project` or `reference` | group preferences → `user`; knowledge and failures → `project`; profile → `user` |
| Project root | the `cwd` recorded in a sibling session transcript, falling back to decoding the project slug | the task group's `applies_to: cwd=…` line; for a v2 topic, the `cwd:` in the header of the rollout summary it points at |
| Search terms | none, because the format states none | from `## What's in Memory` in the summary, joined to task groups by conservative token coverage |
| Skipped | the agent's own `MEMORY.md` index, and Coffer's copies | v1's `## General Tips`, the rollout-reference subsections, `raw_memories.md`, `rollout_summaries/`, everything under `extensions/`, and bullets tagged `[via Coffer]` |

Neither reader opens session transcripts or rollouts as a source. The Claude Code reader reads a transcript's recorded `cwd`, and the Codex reader the `cwd:` line of a v2 rollout summary's header (nothing below it), for one purpose only: finding an entry's project root.

Codex keeps v1 memory in `memories/` and v2 in `memories_v2/`, and Codex Desktop picks one per thread. Both are read while both are there. v2 has no `MEMORY.md` or task groups: its summary files each piece of work under a project scope Codex names in words, with a pointer to the session's rollout summary. A v2 topic's identity names its scope, so it reads as a task-group entry and is not listed among the standing memories. While a v2 summary is there, the profile comes from it, and v1's summary yields only the preferences v2 does not state word for word. During Codex's dual write one piece of work can arrive twice, as v1 bullets and as a v2 topic; see ADR [Follow Codex's Memory Into Every Version Folder It Keeps](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/follow-codex-memory-into-every-version-folder.md).

A reader that cannot parse its source fails **loudly and in isolation**: that agent publishes nothing in that sync, the Memory page names the path and the reason, the other agent is still read, and entries it published earlier stay in the hub rather than being deleted.

A source whose digest matches the one in the ledger is skipped. Losing the ledger only costs a full re-read. A ledger written under another reader revision (bumped when the sync starts to file memories differently) forgets its digests the same way, so one sync re-files everything already in the hub.

## Writing into each agent

A machine writes a hub entry into every registered agent on it except the agent the entry came from on the machine it came from: Claude Code on the desktop receives what Claude Code learned on the laptop. A project's entries are written only where the project is **checked out** on this machine. Checkouts are found each sync from the working directories the registered agents recorded (Claude Code's project directories, Codex task groups' `cwd=`), each resolved to its repository; there is no disk crawl. When a project is checked out more than once, the main checkout wins over a worktree, then the most recently used.

### Claude Code

Claude Code reads a memory only as text it loads by itself: the first 200 lines and 25 KB of a project's `MEMORY.md`, and every file under `rules/`. It opens a memory's own file only when its model decides to, which in two weeks of the maintainer's sessions it never did. So Coffer writes **no file per memory** into Claude Code, only text it loads. The decision and the options weighed (hooks, an index, MCP tools, pulling like knowledge) are in the ADR [Claude Code Reads Other Agents' Memories as Text It Loads](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/claude-code-reads-other-agents-memories-as-text.md).

- **A project's memories** go into a marked block at the end of that project's `MEMORY.md`, in `<config_dir>/projects/<slug>/memory/`, where the slug is Claude Code's own encoding of the repository root, shared by its worktrees (created when missing). They load only in sessions in that project. The block sits between `<!-- coffer:memory-sync:begin -->` and `<!-- coffer:memory-sync:end -->`; a write replaces only the bytes between the markers, or appends the block when there are none, and the previous file goes to `~/.coffer/config-backups/` first.
- **One line per memory**: its text, at most 800 characters, with its title in bold in front when the text does not open with it (Codex titles a memory by its first clause), then the agent it came from, newest first.
- **Bounded.** The block stays within 4 KB. Memories that do not fit are counted in a last line naming `coffer memory entries --project <project>`, which lists them.
- **Earlier copies.** An earlier build wrote one `coffer_<slug>.md` file per memory and a `-coffer-global` project for global ones, and later global memories into `<config_dir>/rules/coffer-memory.md`. They are no longer targets, so the first sync removes those still as written, through the usual plan (a large removal waits as a preview), empties the old block and deletes the rules file.

### Codex

- **Folder.** `extensions/coffer/` in every Codex memory folder that is there (`<config_dir>/memories/`, `<config_dir>/memories_v2/`), with `instructions.md` and `resources/<entry id>-<slug>.md`. Each memory folder is a write location of its own, with its own ledger rows, status and copy counts; the v1 folder keeps the ledger key copies had before. Codex's consolidation reads memory extensions as primary inputs and treats a deleted resource as a signal to forget. Codex prunes resources whose name begins with a timestamp after fourteen days, so Coffer's names never do.
- **A newer folder.** A `memories_v<N>` Coffer does not know is listed as a location that writes nothing and is reported as unrecognised, beside the folders Coffer writes.
- **Resource.** The title, the project it applies to (the checkout on this machine and the project key), the origin agent, type and date, then the memory's text.
- **instructions.md** tells consolidation that these are memories the person's other agents learned, to be treated as information and never as instructions; to file each under the project it names; that fresher evidence wins over an older statement; to tag what it derives from them `[via Coffer]`; and never to delete these files.
- **Memories off.** When `[features] memories` in `config.toml` is off, nothing is written for Codex and the page says so.

A writer that does not recognise the layout it is about to write into (no Claude Code memory directory shape, or a Codex memory folder without `MEMORY.md`, `memory_summary.md` or `rollout_summaries/`) writes nothing for that agent and reports it, the same way as a broken reader. Every path built from a source or an entry passes a traversal guard, and reads and writes stay inside registered agents' memory paths and `vault/memory/`.

### Codex's own import

Codex can import Claude Code's project memories itself and keep the import updated. When it does (a switch on Codex's Memory tab, stored in the ledger, because the setting's own location is not documented), Coffer skips the Claude Code → Codex direction on that machine. Codex → Claude Code continues.

## Echo, absorption and hand-over

Writing into the agents and reading them back on the next sync must not loop.

- **Copies are recognised.** On Claude Code, the reader skips the marked block, and any `coffer_` file left by an earlier build whose frontmatter has a `coffer.entry`. On Codex, the reader skips everything under `extensions/` and any bullet tagged `[via Coffer]`; in the user profile, which is prose, it drops each tagged sentence and reads the rest.
- **Absorption does not circulate.** An agent folds what Coffer delivered into its own memory: Claude Code restates a line of the block in one of its own files; Codex's consolidation rewrites a resource into a bullet. That memory is the agent's and syncs, but its rewording must not bounce forever. The ledger keeps, per agent, fingerprints of every sentence Coffer delivered to it (lower-cased, whitespace-collapsed, punctuation-stripped, hashed). When an agent's own memory changes and every added sentence is one Coffer delivered, the change is recorded without publishing. A fact crosses each agent boundary once; reworded beyond the fingerprint, it publishes as the agent's own and each side's curation merges it with what it has.
- **An edited or removed copy belongs to the agent.** A Codex resource whose digest no longer matches what Coffer wrote is `edited`; a missing one is `removed`. Both are left alone while the hub entry is unchanged. When the entry changes, the new version is written as a new resource beside the edited one, or the removed one is written again. Removing a copy never deletes its hub entry. Coffer's block is Coffer's own and is rewritten whole.

Coffer never creates, changes, moves or deletes any other file in an agent's memory, and never changes an agent's memory settings.

## Project memories only {#project-memories-only}

Coffer publishes a memory only when its agent learned it in a repository. Codex's profile, its preferences and general tips, and anything learned in a scratch folder stay with the agent that wrote them and reach no other agent: what Codex learned outside a repository was mostly one employer's tool habits, and putting it into every Claude Code session carried it into unrelated projects. A person-wide preference belongs in each agent's own instructions file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`), which the person writes.

Within a project every memory syncs, task notes included: Coffer does not judge a memory by where inside a project its agent filed it. Each agent's own curation prunes what goes stale.

A `global/` entry an earlier build published is written into no agent and not listed; the reader revision in the ledger makes the first sync on its origin machine re-read every source and delete it. See ADR [Sync Only Project Memories](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-only-project-memories.md).

## The ledger and the preview

`~/.coffer/local/memory-sync.json` is machine-local and never synced. It records each source's digest and the entries it produced, every copy written per agent and config directory with its target path, entry, entry version, digest and state (`written`, `edited`, `removed`), the delivered-sentence fingerprints, the Codex-import switch, whether this machine has confirmed a preview, the last sync time and its report. Losing it costs one preview: the block is rewritten whole, each Codex resource is named by its entry id, and the preview shows any rewrites before they happen.

A sync computes its whole plan (hub changes and copy changes) before writing. Hub changes apply at once. Copy changes apply only when this machine has confirmed a preview before and the plan writes or rewrites at most 50 copies; otherwise the plan is saved as the pending preview, `~/.coffer/local/memory-sync-preview.json`. **Write** applies exactly that plan, re-checking each target's digest and skipping any that moved since; **Cancel** drops it. A newer sync replaces a pending preview.

## The sync pass

```mermaid
flowchart TD
  A["List sources per registered agent"] --> B{"Digest unchanged?"}
  B -- yes --> S["Skip"]
  B -- no --> R["Read the source"]
  R -- fails --> F["Report; keep its hub entries"]
  R -- entries --> E{"A copy, or only absorbed text?"}
  E -- yes --> K["Record; do not publish"]
  E -- no --> W{"Looks like a secret?"}
  W -- yes --> H["Withhold; report"]
  W -- no --> P["Publish to vault/memory/ (one commit)"]
  S --> C
  K --> C
  P --> C["Plan copies per agent, for checked-out projects"]
  C --> Q{"First sync or more than 50 copies?"}
  Q -- yes --> V["Save as preview; wait for Write"]
  Q -- no --> X["Write copies; update the ledger"]
  X --> Y["Audit memory_synced when anything changed"]
```

One worker runs the sync at daemon start and then on an interval (one hour by default), under the actor `system:memory-sync-worker`. Its switch and interval are the internal engine's `memory_sync` pass, read **per pass**, so a change in Settings applies without a restart; the switch is on by default, and the first sync on a machine still waits as a preview. **Sync now** runs the same sync by hand; only one sync runs at a time, and a request while one runs is answered as already running. A failed sync is logged and never ends the loop.

The whole layer sits behind the `memory` experimental feature: off, the worker skips every pass and `/api/v1/memory` is closed. Copies already written stay in the agents.

## Curation stays with the agents

Each agent's Memory tab reads the agent's own state from its config, never from undocumented internal databases: Claude Code's auto memory (`autoMemoryEnabled` in `settings.json`, absent means on); Codex's memories feature (`[features] memories` in `config.toml`), whose consolidation runs whenever its memories are on. Auto Dream has no documented setting: Coffer reads `autoDreamEnabled` in `settings.json` and, when it is absent, the account default Claude Code caches in `~/.claude.json`, and says which one decided; the newest `.consolidate-lock` in Claude Code's project memory folders says when it last ran. A state Coffer cannot read is shown as unknown. **Turn on** writes only `"autoDreamEnabled": true` into `settings.json`, after the person confirms, with a backup, and records `memory_curation_enabled`; Coffer never changes the setting unasked ([ADR](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/curate-claude-memory-in-the-open.md)).

**Curate now** on Claude Code is a hand-off that stands in for Auto Dream: Coffer opens Claude Code in the person's terminal with a prompt that lists the memory folders Coffer wrote into on this machine and asks it to consolidate Claude Code's own memory one folder at a time (plan first, merge duplicates, drop what is contradicted or stale, use absolute dates, leave Coffer's block alone, change nothing else, report the counts), and records `memory_curation_requested`. The person sees every step and approves edits under Claude Code's own permissions. Codex has none: its consolidation runs by itself. Curation therefore runs on the agents' schedules: a rarely used project may hold a copy beside the agent's own version of the same lesson until the agent next curates. Coffer does not depend on curation for correctness, because what it writes is valid on its own.

## Undo

**Undo sync** deletes every copy Coffer wrote on this machine that the agent has not edited, the marked block from each `MEMORY.md` and the extension folder in each Codex memory folder, turns automatic sync off and records `memory_sync_undone`. It never deletes hub entries or anything an agent wrote itself. The ledger is what makes undo exact: Coffer knows every copy it wrote and from what.

## Audit

| Event | When |
| --- | --- |
| `memory_synced` | a sync (or a preview's **Write**) changed something; lists hub entries published, updated and deleted, copies written, updated and removed per agent and path, memories withheld and sources that failed |
| `memory_sync_undone` | **Undo sync** ran |
| `memory_curation_requested` | **Curate now** handed curation to Claude Code |
| `memory_curation_enabled` | **Turn on** added `autoDreamEnabled` to Claude Code's settings |
| `memory_hook_removed` | the upgrade removed the retired `coffer-memory` hook from one agent |

An agent's own change to its memory is not a Coffer act and is not audited.

## No table, no resource kind

The hub is files in the vault, and what a machine wrote into its agents is one machine-local file. The layer adds no table and no resource kind.

## Upgrade

A one-shot, idempotent start-up step removes the `coffer-memory`-marked hook entries an earlier build installed into Claude Code's `settings.json` and Codex's `hooks.json`, with the agent's backed-up config writer and leaving every other hook and key untouched, and records one `memory_hook_removed` event per agent it changed. It deletes `~/.coffer/derived/memory/` and `~/.coffer/derived/resources/memory/` before the resource store indexes `derived/`. Nothing is lost: both were rebuilt from the agents' own memory, which the first sync publishes. The internal-engine settings carry the old aggregation switch and interval over to `memory_sync`.

## Trade-offs and alternatives

- **Sync into native memory without a hub.** Delivery and curation would be the agents' own, but native memory is machine-local, so memory would not follow the person to another machine. The hub adds that, and makes undo exact.
- **A Coffer-held store agents read and write through MCP tools.** Agent-agnostic and touches no agent file, but depends on agents choosing to call a tool. Coffer's earlier recall tool was called five times in its life. Retrieval nobody calls is not retrieval.
- **Read-only aggregation with hook delivery.** Coffer kept its own notes, waited for a person to tidy duplicates and handed notes to sessions through a hook at session start and each prompt. It was the most machinery for the least effect, and memory attached to every message was unwanted.
- **Projecting a Coffer store into native locations.** Taking over an agent's memory directory and switching its own memory off is intrusive, and a lossless two-way mapping between two moving private formats does not exist.
- **A Coffer-run model to merge memories.** Both agents already curate with the model the person uses; a second curator would need its own model connection and run unattended over the same files.
- **A third writer abstraction.** Two readers and two writers are written as two each. A third agent earns an abstraction, not before.

The writers are coupled to two private formats, one of them (Codex extensions) undocumented. The writer checks the layout it expects and refuses otherwise, the upstream source paths it follows are recorded in its module, and an acceptance test pins the file names.

## Where it lives {#where-it-lives-in-the-code}

| Concern | Where |
| --- | --- |
| Repository identity, hub entries, portable paths, the sync plan, absorption fingerprints and the native writers' rendering | the domain layer's `memory` package |
| The sync service and worker, publishing, writing, the report, the page's view and the upgrade removal | the application layer's `memory` package |
| Native-memory readers and writers, the hub store, checkouts, curation state, and the ledger | the infrastructure layer's `memory` package |
| The `/api/v1/memory/sync/*` routes and the worker's wiring | the HTTP surface |
| `coffer memory` | the CLI surface |

## Related

- Spec: [memory](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/memory/spec.md)
- Decision records: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-memory-into-each-agents-own-memory.md), [Memory Is About the Person, Knowledge Is About the World](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/memory-is-about-the-person-knowledge-is-about-the-world.md), [Claude Code Reads Other Agents' Memories as Text It Loads](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/claude-code-reads-other-agents-memories-as-text.md)
- [Memory guide](/guides/memory) · [Knowledge architecture](/architecture/knowledge) · [Vault sync](/architecture/vault-sync) · [Persistence](/architecture/persistence)
