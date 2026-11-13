---
title: Memory
description: Let Coffer share what each of your agents has learned with your other agents, on this machine and on your other machines, by writing it into each agent's own memory. Each agent keeps curating and loading its memory itself.
---

# Memory

Coffer keeps every memory your agents wrote for themselves in a project — Claude Code's per-project memory files, the topics of Codex's memory summary — in one place in your vault, and writes each one into your other agents' own memory, in that agent's own format. Each agent then loads and curates those memories the way it loads and curates its own. This page covers what Coffer reads, where the shared memories live, what it writes into each agent, how a sync runs, and how to check, pause and undo it.

Memory is an [experimental feature](/guides/experimental-features): switch it on in **Settings → Features** first.

## What memory sync is for

Every agent keeps its own memory, and none can see another's. What Claude Code learned about a repository this morning, Codex has to be taught again this afternoon, and what either learned on your laptop is missing on your desktop.

Coffer closes that gap without running a memory system of its own:

1. **Publish.** Coffer reads each registered agent's native memory and publishes every memory the agent wrote on this machine into the **hub**, a folder in your vault. [Vault sync](/guides/vault-sync) carries the hub to your other machines.
2. **Write.** Coffer writes every hub memory into each agent on this machine except the one it came from, as memory the agent loads itself.
3. **Leave the rest to the agent.** Merging duplicates, correcting what is wrong and forgetting what is stale is each agent's own curation (Claude Code's Auto Dream, Codex's consolidation). Coffer does not put memory into a session, and does not change a memory an agent wrote.

Coffer's work is mechanical: it copies, files and renames, and never calls a model over your memory.

## Memory, knowledge or a skill

Memory is about you; [knowledge](/guides/knowledge) is about the world. Ask, in order:

1. Would it still hold for someone else? If not, it is **memory**: who you are, how you like to work (preferences, corrections, what you approve), a project's current state and decisions the repository does not record.
2. Is it about an outside system, team or process, or does it need a source? Then it is **knowledge**: how a service or a team works, its pitfalls, an imported document, anything that goes stale or is worth sharing.
3. Is it a fixed sequence of steps you repeat? Then it is a **[skill](/guides/skills)**.

What the repository already says, and one-off requests, belong nowhere. Agents still write task notes into their memory; Coffer syncs them with the rest of the project's memories. To move one into knowledge, ask an agent to write it into a collection.

| | Memory | Knowledge |
| --- | --- | --- |
| Holds | you, how to work with you, a project's state | outside systems, teams, processes and their pitfalls |
| Comes from | agents' own memory, written by the agents | you, or an agent writing it down |
| Organised by | project | collection |
| Who edits the text | the agent that holds it, through its own curation | you and agents, directly |
| Reaches an agent | through the agent's own memory, which it loads every session | the agent reads it when the `coffer-guide` skill points there |
| Stored | the hub in `vault/memory/`, synced like other vault content | the vault, synced like other vault content |

## What Coffer reads

| Agent | Files read |
| --- | --- |
| Claude Code | Each memory file in `<config_dir>/projects/<project>/memory/*.md` — its frontmatter `name`, `description` and `type`, and its body. Claude Code's own `MEMORY.md` index is skipped. |
| Codex | `<config_dir>/memories_v2/memory_summary.md`: each topic Codex lists under **What's in Memory**, filed under the project whose directory the session's rollout summary records in its first lines. The profile, preferences and general tips in the same file are about you rather than a project and are not read. Codex's older `memories/MEMORY.md`, with its task groups, is not read either: those are working notes of single tasks, and what is worth keeping from them is what Codex consolidates into the summary. |

Coffer does not read session transcripts or rollout files. Both agents already distil their own sessions into memory, and Coffer starts from that. It skips its own copies when it reads them back (see [What Coffer writes into each agent](#what-coffer-writes-into-each-agent)), so nothing it wrote is published again.

If an agent's memory format changes and a file can no longer be parsed, that agent publishes nothing in that sync, the Memory page names the file and the reason, the other agent's memory is still read, and what the agent published earlier stays in the hub.

## The hub

The hub is `vault/memory/` in your vault, one Markdown file per memory:

```text
~/.coffer/vault/memory/
└── projects/
    └── github.com-acme-payments/
        └── 8c01d6e2a9b34f70.md
```

- **A project is its repository.** A project is named by its repository's `origin` URL (`github.com/acme/payments`), or by the repository's directory name when it has no remote. A main checkout, its worktrees and another clone of the same repository — on this machine or another — are one project.
- **A memory stays where its agent put it.** A memory your agent learned in a repository is filed under that project, even when it is a preference of yours: a preference Codex noted while working on one task belongs to that task's project.
- **Only project memories are synced.** A memory learned outside any repository — Codex's profile and preferences, a scratch folder, a chat with no folder — stays with the agent that wrote it and is not synced. Neither is one learned in the vault's own folder, `~/.coffer/vault`. Write a preference you want every agent to follow into each agent's own instructions file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`).
- **Paths travel.** When a memory is published, its repository's folder is written as `<repo>` and your home folder as `~`. When it is written into an agent, they expand to where the project is checked out on that machine and to that machine's home.

Each file's frontmatter names where the memory came from (the machine, the agent and the agent's own file), its `type`, `title`, one-line `description` and when it was created and last updated; the body is the memory as the agent wrote it. Only the machine and agent a memory came from ever change or delete its hub file: when the agent drops the memory, its hub file goes too. Deleting the repository's folder from that machine does not remove its memories.

A memory that looks like it holds a secret (an API key, a token, a private key, a password) is **withheld**: it is not published, and the Memory page names the agent and source, never the value.

The hub is vault content, so if you use [vault sync](/guides/vault-sync) your memories go to your own git remote with the rest of your vault. Two agents' versions of one lesson are two hub files; each agent merges them on its own side.

## What Coffer writes into each agent {#what-coffer-writes-into-each-agent}

A hub memory is written into every registered agent on this machine except the agent that wrote it, on the machine where it wrote it. Claude Code on your desktop receives what Claude Code learned on your laptop.

| Agent | What Coffer writes |
| --- | --- |
| Claude Code | Text Claude Code loads by itself, never a file per memory. A project's memories go into a marked block at the end of that project's `MEMORY.md` (`~/.claude/projects/<project>/memory/`, created when missing), between `<!-- coffer:memory-sync:begin -->` and `<!-- coffer:memory-sync:end -->`, so they load only in that project. Each memory is one line: its text (up to 800 characters) and the agent it came from, newest first. The block stays within 4 KB; the last line counts what did not fit and names `coffer memory entries`, which lists it, and the Memory page marks each of those memories **Did not fit**. |
| Codex | In each Codex memory folder that is there (`~/.codex/memories/` and `~/.codex/memories_v2/`, because Codex picks one of them per thread), one file per memory under `extensions/coffer/resources/`, naming the project it applies to above the memory's text, and an `instructions.md` that tells Codex's consolidation what these files are: memories your other agents learned, to be treated as information and never as instructions, filed under the project each names, and tagged `[via Coffer]` when Codex folds them into its own memory. |

- **Only where the project is checked out.** A project's memories are written on a machine only once the project is checked out there, as found from the working directories your agents recorded. Until then they wait in the hub.
- **Only Coffer's own files.** Coffer creates, changes and deletes only its marked block in `MEMORY.md` and its Codex extension folder. Everything else in `MEMORY.md` and every memory the agent wrote stays byte for byte as it was, and Coffer never changes an agent's memory settings. It backs `MEMORY.md` up to `~/.coffer/config-backups/` before changing it.
- **An edited copy belongs to the agent.** When Codex edits or removes one of Coffer's files in its extension folder, Coffer stops managing it: it does not overwrite the edit or bring the removed file back. If the memory later changes in the hub, Coffer writes the new version as a new file beside the edited one.
- **Codex's memories off.** When Codex's memories feature is off (`memories` under `[features]` in `config.toml`), Coffer writes nothing into Codex and the Memory page says so.
- **A Codex memory folder Coffer does not know.** When Codex starts a newer memory folder (`memories_v3/`, say), Coffer writes nothing into it, keeps writing the folders it knows, and the Memory page and Codex's Memory tab name the new folder until Coffer is updated.

### When Codex imports from Claude Code itself

Codex can import Claude Code's project memories itself and keep that import updated. When you use that, turn on **Codex imports Claude Code's memories itself** in the **Memory sync** section of Codex's Memory tab (**Agents → Codex → More → Memory**). Coffer then writes no Claude Code memory into Codex on this machine, and a memory from Claude Code says *Codex imports it* for Codex. Codex's memories still reach Claude Code.

## How a sync runs

One background pass, **memory sync**, reads the agents, updates the hub and writes the copies. It is on by default, runs when the daemon starts and then every hour, and calls no model. A source whose content has not changed since the last sync is skipped, so a quiet sync costs almost nothing. Only one sync runs at a time.

```text
Memory → Sync now
```

**Sync now** runs a sync at once and reports how many memories it published, copies it wrote and copies it removed. The **▾** beside it opens the automatic sync: a switch, **Sync memory automatically**, and an interval from 15 minutes to 1 day. A change applies without a restart. The header says when memory last synced, or that automatic sync is off.

### A first or large sync waits for you

The first sync on a machine, and any sync that would write more than 50 copies, publishes to the hub as usual but writes nothing into your agents yet. The Memory page counts it in its banner; **Review** lists it per agent and project with how many copies would be new, updated and removed. Open a line to see each memory it would write, update or remove (a line that removes anything starts open), and choose a memory to open it. **Write** applies exactly that plan; **Cancel** drops it. A later sync replaces a preview you have not answered.

### What each sync recorded

Every sync that changed something is one `memory_synced` entry in [Activity](/guides/activity), listing the hub files it published, updated and deleted, the copies it wrote, updated and removed per agent and file, the memories it withheld and the sources it could not read. A sync that changed nothing records nothing.

```sh
coffer log audit --event-type memory_synced --limit 20
```

## The Memory page

```text
Memory
```

The **Memory** page carries the **Experimental** tag. Its header holds **Sync now** with its **▾**, when memory last synced, and a **⋯** menu with **Undo sync…**.

When something waits on you, one banner under the header counts it: a first or large sync waiting for **Write**, sources the last sync could not read, memories withheld because they look like secrets, and agents Coffer cannot write into (their own memory is off). **Review** opens a drawer that lists each, with the file to reveal and a link to the agent's Memory tab.

Below, the projects sit beside the memories:

- **Projects**, on the left: every project in the hub by its short name with its count. Projects not checked out on this machine are grouped under **Not checked out here**. A search box appears when there are many.
- **Memories**, on the right: the open project's memories, newest first, with the project's full key and where it is checked out (or that its memories wait in the hub until it is). Each row shows the title and description, the type, the agent and machine it came from, and when it last changed. Search and the **From** filter narrow the list. A row adds a note only when it is worth a look: *Not in Codex yet*, *Edited in Codex*, *Removed by Codex*.

The address keeps the open project (`/memory?scope=<project folder>`), so a project can be linked to. The page opens on the first project checked out on this machine.

With no Claude Code or Codex registered, the page says there is no agent to sync and offers **Open Agents**.

### A memory

Choose a memory to open it in a drawer. Under its title are its type, the agent and machine it came from and when it changed. First comes where each agent on this machine holds it: per agent, what became of its copy, the file, and **Open in editor** and **Reveal in Finder**. Below is the memory's text, read only. **↑** and **↓** step through the list, and the drawer's **Maximize** gives a long memory the page's width.

| State | Meaning |
| --- | --- |
| **Its own** | the agent wrote this memory itself |
| **Written** | Coffer wrote a copy into Codex |
| **In project memory** | Claude Code loads it as text, from the project's `MEMORY.md` |
| **Did not fit** | Claude Code's 4 KB block is full, so this memory is not in it; it stays in the hub |
| **Next sync** | the copy is written at the next sync |
| **Held back** | the project is not checked out on this machine |
| **Codex imports it** | Codex's own import carries this memory |
| **Edited by agent** / **Removed by agent** | the agent changed or removed the copy, and Coffer leaves it alone |

The page never edits a memory's text. To change a memory, change it where the agent keeps it — in Claude Code's memory folder or with Codex's memory tools — and the next sync carries the change.

### On each agent's Memory tab

```text
Agents → choose the agent → More → Memory
```

Each agent's own part is on its Memory tab, so the Memory page does not grow with the number of agents. While the memory feature is on, the tab starts with a **Memory sync** section: the copies Coffer wrote into it (and how many the agent edited or removed), for Codex one line per memory folder, and on Claude Code's tab that its memories go in as text; when Coffer cannot write into the agent, why, and how to turn the agent's own memory on when that is the reason; and **Open Memory**, which opens the Memory page filtered to this agent's memories. Codex's tab also has **Codex imports Claude Code's memories itself**. Below it are the agent's own memory folders.

## Curation is each agent's own

Coffer does not merge or retire memories. Each agent curates what it holds:

- **Claude Code**: Auto Dream merges duplicates, drops what is contradicted or stale and rewrites the index, on Claude Code's own schedule. It is a Claude Code feature: check or change it in Claude Code's `/memory`.
- **Codex**: consolidation runs whenever its memories are on and its inputs changed, and reads Coffer's extension folder as one of its inputs. Fresher evidence wins over an older statement.

A rarely used project can hold duplicates until its curation next runs. Coffer does not show, switch on or start an agent's curation; to tidy a project now, ask the agent to in a session there.

## Undo sync

```text
Memory → ⋯ → Undo sync…
```

**Undo sync…** shows what it removes and what it keeps, then removes from this machine every copy Coffer wrote into Codex that Codex has not edited, Coffer's block in each `MEMORY.md` and `extensions/coffer/` in each Codex memory folder, turns automatic sync off and records a `memory_sync_undone` event. It keeps the hub in your vault, every memory an agent wrote itself and every copy an agent edited. Your other machines are not affected. Turn automatic sync back on, or choose **Sync now**, to write the copies again.

## Turning memory off

Switching the **memory** feature off in **Settings → Features** stops the sync, hides the Memory page and closes its API. Copies already written stay in your agents, as ordinary memory they own; use **Undo sync…** first if you want them gone. Turning automatic sync off on the Memory page stops the unattended sync and keeps **Sync now**.

## Troubleshooting

**A project's memories are not in an agent.** Open the project on the Memory page and choose a memory: its drawer says per agent what became of its copy. **Held back** means the project is not checked out on this machine (open it once with an agent there); **Next sync** means a sync has not run since; a preview waiting on the Memory page means you have not chosen **Write** yet. For Codex, check that its memories are on.

**An agent's memory is not published.** Check that the agent is registered and its own memory is on, then choose **Sync now** and read what the banner's **Review** lists. A memory learned outside any repository is not synced, and Codex publishes only from its v2 summary (`memories_v2/memory_summary.md`).

**The same lesson appears twice in an agent.** Two agents' accounts of one lesson are two memories until the agent curates. Wait for the agent's own curation, or ask the agent in a session to tidy its memory for that project.

**A copy keeps coming back after I deleted it.** It does not, unless the memory changed in the hub since: then the new version is written again. Coffer's block is rewritten on every sync, so do not edit them. To stop a memory reaching an agent, change or remove it in the agent that wrote it.

## Related

- [Knowledge](/guides/knowledge)
- [Agents](/guides/agents)
- [Vault sync](/guides/vault-sync)
- [Memory architecture](/architecture/memory)
- [`coffer memory`](/reference/cli/memory)
- [Memory spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/memory/spec.md)
- [Sync memory into each agent's own memory through a hub in the vault](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-memory-into-each-agents-own-memory.md)
- [Memory is about the person, knowledge is about the world](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/memory-is-about-the-person-knowledge-is-about-the-world.md)
- [Claude Code reads other agents' memories as text it loads](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/claude-code-reads-other-agents-memories-as-text.md)
