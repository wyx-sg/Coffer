---
title: Memory
description: Let Coffer share what each of your agents has learned with your other agents, on this machine and on your other machines, by writing it into each agent's own memory. Each agent keeps curating and loading its memory itself.
---

# Memory

Coffer keeps every memory your agents wrote for themselves — Claude Code's per-project memory files, Codex's task groups and profile — in one place in your vault, and writes each one into your other agents' own memory, in that agent's own format. Each agent then loads and curates those memories the way it loads and curates its own. This page covers what Coffer reads, where the shared memories live, what it writes into each agent, how a sync runs, and how to check, pause and undo it.

Memory is an [experimental feature](/guides/experimental-features): switch it on in **Settings → Features** first.

## What memory sync is for

Every agent keeps its own memory, and none can see another's. What Claude Code learned about a repository this morning, Codex has to be taught again this afternoon, and what either learned on your laptop is missing on your desktop.

Coffer closes that gap without running a memory system of its own:

1. **Publish.** Coffer reads each registered agent's native memory and publishes every memory the agent wrote on this machine into the **hub**, a folder in your vault. [Vault sync](/guides/vault-sync) carries the hub to your other machines.
2. **Write.** Coffer writes every hub memory into each agent on this machine except the one it came from: as memory files the agent loads itself.
3. **Leave the rest to the agent.** Merging duplicates, correcting what is wrong and forgetting what is stale is each agent's own curation (Claude Code's Auto Dream, Codex's consolidation). Coffer does not put memory into a session, and does not change a memory an agent wrote.

Coffer's work is mechanical: it copies, files and renames, and never calls a model over your memory.

Memory is not [knowledge](/guides/knowledge). Knowledge is what you or an agent deliberately wrote down about the world; memory is what agents learned while working, collected automatically.

| | Memory | Knowledge |
| --- | --- | --- |
| Comes from | agents' own memory, written by the agents | you, or an agent writing it down |
| Organised by | project, plus `global` | collection |
| Who edits the text | the agent that holds it, through its own curation | you and agents, directly |
| Reaches an agent | through the agent's own memory, which it loads every session | the agent reads it when the `coffer-guide` skill points there |
| Stored | the hub in `vault/memory/`, synced like other vault content | the vault, synced like other vault content |

## What Coffer reads

| Agent | Files read |
| --- | --- |
| Claude Code | Each memory file in `<config_dir>/projects/<project>/memory/*.md` — its frontmatter `name`, `description` and `type`, and its body. Claude Code's own `MEMORY.md` index is skipped. |
| Codex | `<config_dir>/memories/MEMORY.md` — each task group's preferences, reusable knowledge and failures — and `memory_summary.md` — the profile, standing preferences, and the search terms Codex lists for each task group. |

Coffer does not read session transcripts or rollout files. Both agents already distil their own sessions into memory, and Coffer starts from that. It skips its own copies when it reads them back (see [What Coffer writes into each agent](#what-coffer-writes-into-each-agent)), so nothing it wrote is published again.

If an agent's memory format changes and a file can no longer be parsed, that agent publishes nothing in that sync, the Memory page names the file and the reason, the other agent's memory is still read, and what the agent published earlier stays in the hub.

## The hub

The hub is `vault/memory/` in your vault, one Markdown file per memory:

```text
~/.coffer/vault/memory/
├── global/
│   └── 3f2a91c4de55b071.md
└── projects/
    └── github.com-acme-payments/
        └── 8c01d6e2a9b34f70.md
```

- **A project is its repository.** A project is named by its repository's `origin` URL (`github.com/acme/payments`), or by the repository's directory name when it has no remote. A main checkout, its worktrees and another clone of the same repository — on this machine or another — are one project.
- **What is about you is `global`.** A memory about you rather than a project (type `user`: your preferences, Codex's profile) is filed under `global`, whichever repository it came from.
- **Scratch folders are not projects.** A memory learned in a directory that is not inside a repository is published only when it is about you, under `global`.
- **Paths travel.** When a memory is published, its repository's folder is written as `<repo>` and your home folder as `~`. When it is written into an agent, they expand to where the project is checked out on that machine and to that machine's home.

Each file's frontmatter names where the memory came from (the machine, the agent and the agent's own file), its `type`, `title`, one-line `description` and when it was created and last updated; the body is the memory as the agent wrote it. Only the machine and agent a memory came from ever change or delete its hub file: when the agent drops the memory, its hub file goes too.

A memory that looks like it holds a secret (an API key, a token, a private key, a password) is **withheld**: it is not published, and the Memory page names the agent and source, never the value.

The hub is vault content, so if you use [vault sync](/guides/vault-sync) your memories go to your own git remote with the rest of your vault. Two agents' versions of one lesson are two hub files; each agent merges them on its own side.

## What Coffer writes into each agent {#what-coffer-writes-into-each-agent}

A hub memory is written into every registered agent on this machine except the agent that wrote it, on the machine where it wrote it. Claude Code on your desktop receives what Claude Code learned on your laptop.

| Agent | What Coffer writes |
| --- | --- |
| Claude Code | One file per memory, `coffer_<slug>.md`, in the project's memory folder (`~/.claude/projects/<project>/memory/`, created when missing), in Claude Code's own memory format plus a `coffer:` block naming the memory's origin. One line per copy inside a marked block at the end of that folder's `MEMORY.md`, between `<!-- coffer:memory-sync:begin -->` and `<!-- coffer:memory-sync:end -->`: at most 30 lines, newest first, the last line saying how many more copies the folder holds. `global` memories go to `~/.claude/rules/coffer-memory.md`, which Claude Code loads in every session. |
| Codex | One file per memory under `~/.codex/memories/extensions/coffer/resources/`, naming the project it applies to (or "all projects") above the memory's text, and an `instructions.md` that tells Codex's consolidation what these files are: memories your other agents learned, to be treated as information and never as instructions, filed under the project each names, and tagged `[via Coffer]` when Codex folds them into its own memory. |

- **Only where the project is checked out.** A project's memories are written on a machine only once the project is checked out there, as found from the working directories your agents recorded. Until then they wait in the hub. `global` memories are written on every machine.
- **Only Coffer's own files.** Coffer creates, changes and deletes only its copies, its marked block in `MEMORY.md`, its rules file and its Codex extension folder. Everything else in `MEMORY.md` and every memory the agent wrote stays byte for byte as it was, and Coffer never changes an agent's memory settings. It backs `MEMORY.md` up to `~/.coffer/config-backups/` before changing it.
- **An edited copy belongs to the agent.** When an agent edits or removes a copy — Auto Dream merging it into one of Claude Code's own files, say — Coffer stops managing it: it does not overwrite the edit or bring the removed copy back. If the memory later changes in the hub, Coffer writes the new version as a new copy beside the edited one.
- **Codex's memories off.** When Codex's memories feature is off (`memories` under `[features]` in `config.toml`), Coffer writes nothing into Codex and the Memory page says so.

### When Codex imports from Claude Code itself

Codex can import Claude Code's project memories itself and keep that import updated. When you use that, turn on **Codex imports Claude Code's memories itself** under the agents table on the Memory page. Coffer then writes no Claude Code memory into Codex on this machine, and the table says *Codex imports it*. Codex's memories still reach Claude Code.

## How a sync runs

One background pass, **memory sync**, reads the agents, updates the hub and writes the copies. It is on by default, runs when the daemon starts and then every hour, and calls no model. A source whose content has not changed since the last sync is skipped, so a quiet sync costs almost nothing. Only one sync runs at a time.

```text
Memory → Sync now
```

**Sync now** runs a sync at once and reports how many memories it published, copies it wrote and copies it removed. The **▾** beside it opens the automatic sync: a switch, **Sync memory automatically**, and an interval from 15 minutes to 1 day. A change applies without a restart. The header says when memory last synced, or that automatic sync is off.

### A first or large sync waits for you

The first sync on a machine, and any sync that would write more than 50 copies, publishes to the hub as usual but writes nothing into your agents yet. The Memory page shows it as a preview: per agent and project, how many copies would be written, updated and removed. Open a row to see the project's memories. **Write** applies exactly that plan; **Cancel** drops it. A later sync replaces a preview you have not answered.

### What each sync recorded

Every sync that changed something is one `memory_synced` entry in [Activity](/guides/activity), listing the hub files it published, updated and deleted, the copies it wrote, updated and removed per agent and file, the memories it withheld and the sources it could not read. A sync that changed nothing records nothing.

```sh
coffer log audit --event-type memory_synced --limit 20
```

## The Memory page

```text
Memory
```

The **Memory** page carries the **Experimental** tag. Its header holds **Sync now** with its **▾**, when memory last synced, and a **⋯** menu with **Undo sync…**. Below it, in order:

- **Problems**: sources the last sync could not read, and memories withheld because they look like secrets.
- **The preview**, while a first or large sync waits for **Write** or **Cancel**.
- **Projects**: every project in the hub, with whether and where it is checked out on this machine (**Not checked out here** otherwise), how many memories it holds and the agents they came from. **Global memories** sits at the top. A search box filters the rows.
- **Agents on this machine**: per agent, the copies written here (and how many the agent edited or removed), whether its own memory is on (Claude Code's auto memory, Codex's memories) and whether its own curation is on (Claude Code's Auto Dream, Codex's consolidation), with a hint when either is off, and **Curate now**. With Codex registered, the switch **Codex imports Claude Code's memories itself** sits below the table.

With no Claude Code or Codex registered, the page says there is no agent to sync and offers **Open Agents**.

Choose a project to open its page. It names where the project is checked out on this machine, or that its memories wait in the hub because it is not, and lists every memory: its title and type, the agent and machine it came from, when it was last updated, and per agent on this machine what became of its copy:

| State | Meaning |
| --- | --- |
| **Its own** | the agent wrote this memory itself |
| **Written** | Coffer wrote a copy (**In rules file** for a `global` memory in Claude Code) |
| **Next sync** | the copy is written at the next sync |
| **Held back** | the project is not checked out on this machine |
| **Codex imports it** | Codex's own import carries this memory |
| **Edited by agent** / **Removed by agent** | the agent changed or removed the copy, and Coffer leaves it alone |

The page never edits a memory's text. To change a memory, change it where the agent keeps it — in Claude Code's memory folder or with Codex's memory tools — and the next sync carries the change. To see an agent's own memory folders, open **Agents → choose the agent → More → Memory**.

## Curation is each agent's own

Coffer does not merge or retire memories. Each agent curates what it holds, Coffer's copies included:

- **Claude Code**: Auto Dream merges duplicates, drops what is contradicted or stale and rewrites the index, on Claude Code's own schedule. Coffer cannot read whether it is on yet, so the page shows it as unknown; check it in Claude Code's `/memory`.
- **Codex**: consolidation runs whenever its memories are on and its inputs changed, and reads Coffer's extension folder as one of its inputs. Fresher evidence wins over an older statement.

A rarely used project can hold a copy beside the agent's own version of the same lesson until its curation next runs. To run it now, choose **Curate now** on the agent's row: Coffer starts the agent without a terminal, in your home folder, with a prompt asking it to consolidate its own memory, and records a `memory_curation_requested` event. The run uses that agent's own model and account, as any session with it does.

## Undo sync

```text
Memory → ⋯ → Undo sync…
```

**Undo sync…** shows what it removes and what it keeps, then removes from this machine every copy Coffer wrote that the agent has not edited, Coffer's block in each `MEMORY.md`, `~/.claude/rules/coffer-memory.md` and `~/.codex/memories/extensions/coffer/`, turns automatic sync off and records a `memory_sync_undone` event. It keeps the hub in your vault, every memory an agent wrote itself and every copy an agent edited. Your other machines are not affected. Turn automatic sync back on, or choose **Sync now**, to write the copies again.

## Turning memory off

Switching the **memory** feature off in **Settings → Features** stops the sync, hides the Memory page and closes its API. Copies already written stay in your agents, as ordinary memory they own; use **Undo sync…** first if you want them gone. Turning automatic sync off on the Memory page stops the unattended sync and keeps **Sync now**.

## Upgrading from an earlier build

Earlier builds kept memory as notes under `~/.coffer/derived/memory/` and handed them to sessions through a `coffer-memory` hook. On its first start, the daemon removes that hook from every agent's settings (leaving every other hook untouched, and recording a `memory_hook_removed` event per agent) and deletes `~/.coffer/derived/memory/`. Nothing is lost: those notes were built from the agents' own memory, which the first sync publishes to the hub.

## Troubleshooting

**A project's memories are not in an agent.** Open the project's page: **Held back** means the project is not checked out on this machine (open it once with an agent there); **Next sync** means a sync has not run since; a preview waiting on the Memory page means you have not chosen **Write** yet. For Codex, check that its memories are on.

**An agent's memory is not published.** Check that the agent is registered and its own memory is on, then choose **Sync now** and read the **Problems** above the projects. A memory learned outside any repository is published only when it is about you.

**The same lesson appears twice in an agent.** Two agents' accounts of one lesson are two memories until the agent curates. Choose **Curate now** on the agent, or wait for its own curation to run.

**A copy keeps coming back after I deleted it.** It does not, unless the memory changed in the hub since: then the new version is written as a new copy. To stop a memory reaching an agent, change or remove it in the agent that wrote it.

## Related

- [Knowledge](/guides/knowledge)
- [Agents](/guides/agents)
- [Vault sync](/guides/vault-sync)
- [Memory architecture](/architecture/memory)
- [`coffer memory`](/reference/cli/memory)
- [Memory spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/memory/spec.md)
- [Sync memory into each agent's own memory through a hub in the vault](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-memory-into-each-agents-own-memory.md)
