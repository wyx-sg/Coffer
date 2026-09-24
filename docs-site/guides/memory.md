---
title: Memory
description: Let Coffer read what each of your agents has learned, distil it into one set of notes per repository, and hand every agent the index.
---

# Memory

Coffer reads the memory your agents already keep — Claude Code's per-project notes, Codex's task groups and profile — distils it into one set of notes per repository plus one global set, and makes those notes available to every agent. It never writes back into an agent's own memory. This page covers what Coffer reads, where the notes live, how agents receive them, and how to browse, switch off and rebuild them.

::: warning Experimental feature
Memory is an [experimental feature](/guides/experimental-features) with the key `memory`. It is on by default in `dev` builds and off by default in `stable` builds. Switch it on under **Settings → General → Experimental features**, or run `coffer daemon features enable memory`. While it is off, the Memory page, the `/api/v1/memory` routes and the `coffer__recall` tool are unavailable, and Coffer removes its session-start hook from every agent that had one; switching memory back on reinstalls the hook in those same agents. Nothing already distilled is deleted.
:::

## What memory aggregation is for

Every agent keeps its own memory, and none can see another's. What Claude Code learned about a repository this morning, Codex has to be taught again this afternoon.

Coffer closes that gap without taking over either agent's memory:

1. **Read.** Coffer reads each registered, enabled agent's native memory files. It never creates, changes, moves or deletes anything there, and never changes an agent's memory settings.
2. **Distil.** Coffer's own model turns what it read into notes in Coffer's own words — one topic per file — merging lessons that two agents learned separately into one note.
3. **Deliver.** At session start, an installed hook hands the agent the index of the notes for the repository it is working in, plus the global notes, and the path where the full notes are.

Memory is not [knowledge](/guides/knowledge). Knowledge is what you or an agent deliberately wrote down about the world; memory is what agents learned while working, collected automatically.

| | Memory | Knowledge |
| --- | --- | --- |
| Comes from | agents' own memory files, read-only | you, or an agent writing it down |
| Organised by | repository, plus `global` | collection |
| Who writes the stored text | Coffer, distilling | you and agents, directly |
| Reaches an agent | the index at session start, through a hook | the agent reads it when the `coffer-guide` skill points there |
| If the store is lost | rebuilt from the agents' own memory | gone |

## What Coffer reads

| Agent | Files read |
| --- | --- |
| Claude Code | Each fact file in `<config_dir>/projects/<project>/memory/*.md` — its frontmatter `name`, `description` and `type`, and its body. Claude Code's own `MEMORY.md` index is skipped. |
| Codex | `<config_dir>/memories/MEMORY.md` — each task group's preferences, reusable knowledge and failures — and `memory_summary.md` — the profile, standing preferences, and the search terms Codex lists for each task group. |

Coffer does not read session transcripts or rollout files. Both agents already distil their own sessions into memory, and Coffer starts from that.

If an agent's memory format changes and a file can no longer be parsed, that agent contributes nothing to the pass, the failure is reported with the file's path and the reason, the other agent's memory is still read, and notes from earlier passes are left in place.

## Partitions

A **partition** is a folder under `~/.coffer/memory/`. There is one per repository, plus one named `global`:

- An entry is filed under the repository it was learned in. The main checkout, its worktrees and another clone of the same repository all map to one partition, named after the repository's directory.
- An entry about **you** rather than a project (type `user`: your preferences, Codex's profile) is filed under `global`, whichever repository it came from.
- Guidance on how to work (type `feedback`) is filed with the repository it was given in, because it usually binds that repository. Only feedback given outside any repository goes to `global`.
- An entry learned in a directory that is not a repository creates no partition. The distil pass decides whether it belongs in `global` or nowhere.

Partitions are created by aggregation only; you do not create them.

```text
~/.coffer/memory/
├── global/
└── payments-api/
    ├── MEMORY.md      ← the index: one line per note
    ├── notes/         ← Coffer's notes, one topic per file
    │   └── retry-budget-for-ledger-writes.md
    ├── RETIRED.md     ← notes that were retired, and why
    └── .raw/          ← what was read from the agents, verbatim (hidden)
```

| File | What it holds |
| --- | --- |
| `MEMORY.md` | The index. Each line gives a note's title, its file, a one-line description written to stand on its own, and the search terms the source supplied, newest first. This is what a session receives. |
| `notes/<slug>.md` | One note. Frontmatter carries `title`, `description`, `type` (`user`, `feedback` or `project`), `origins` (every agent file the note was built from), `created_at` and `updated_at`, and sometimes `search_terms`. The body is Coffer's own wording. |
| `RETIRED.md` | Each retired note's title, the reason, and the note that replaced it. The next pass reads this file so a retired subject is not brought back from the same unchanged source. |
| `.raw/` | Every entry exactly as it was read, with the agent, source path and read time. It is the distil pass's input and lets you check a note against the words it came from. |

Everything under `~/.coffer/memory/` is derived. It can be deleted and rebuilt at any time, and it is not carried by [vault sync](/guides/vault-sync): each machine builds its own from the agents installed on it. To move the memory root, set `COFFER_MEMORY_ROOT` in the daemon's environment.

## How the passes run

Two background passes keep the partitions current. Both are on by default.

| Pass | What it does | Default schedule | Uses a model |
| --- | --- | --- | --- |
| **Read from agents** (aggregation) | Reads every enabled agent's memory files and writes new entries into `.raw/`. A source file whose content has not changed since the last pass is skipped. | At daemon start, then hourly | No |
| **Distil memory** | For each partition, routes new entries against the index — merge into a note, open a new note, retire a note, or keep nothing — then rewrites only the notes that changed, and rewrites `MEMORY.md`. | About a minute after start, then every 6 hours | Yes, when configured |

The two passes run on separate timers: distil does not wait for an aggregation, and a partition with no new entries since its last distil costs no model call. Distil is incremental: the routing request carries the new entries and the index lines, never the note bodies, and each touched note is rewritten in its own small request. Two agents' entries about the same lesson, however differently worded, end up in one note whose `origins` name both.

**Without an internal model.** If Coffer's model is not configured (see [Model providers](/guides/providers)), distil still runs, mechanically: each entry becomes a note of its own and `MEMORY.md` is written from their frontmatter. You get a thinner index, not an empty one, and no model is called.

::: info What leaves your machine
Only the distil pass sends memory content anywhere, and only to the model endpoint you configured. Aggregation, delivery and recall send nothing.
:::

### Change the schedule

Under **Settings → Coffer's model → Automatic upkeep**, each pass has a switch and an interval. On the CLI:

```sh
coffer engine upkeep list
coffer engine upkeep set aggregate --interval 1800
coffer engine upkeep set distil --off
coffer engine upkeep set distil --default-interval
```

A change applies without a restart. The shortest interval is 60 seconds.

### Run a pass now

::: code-group

```sh [CLI]
coffer memory sync                    # read from every agent
coffer memory distil payments-api     # distil one partition
```

```text [Web UI]
Memory → Read from agents
Memory → choose the partition → Distil
```

:::

`coffer memory sync` reports how many entries it read across how many partitions, and any sources that failed to parse. Only one distil pass runs per partition at a time; a request while one is running is refused with `UPKEEP_ALREADY_RUNNING`. `coffer engine upkeep runs` shows what is running now.

## How agents receive memory

### At session start, through a hook

Delivery goes through each agent's own hook mechanism, and you install it explicitly, per agent. Coffer never installs it on its own.

::: code-group

```sh [CLI]
coffer memory delivery                      # installed or not, per agent
coffer memory delivery-install claude-code
coffer memory delivery-install codex
coffer memory delivery-remove codex
```

```text [Web UI]
Agents → choose the agent → Memory tab → Delivery → Install
```

:::

What gets installed:

| Agent | Settings file | Event |
| --- | --- | --- |
| Claude Code | `~/.claude/settings.json` | `SessionStart` (on startup, resume, clear and compact), with a 10-second timeout |
| Codex | `~/.codex/hooks.json` | `UserPromptSubmit`, guarded to fire once per session, because Codex has no session-start event |

The entry runs `coffer memory context --agent-uid <uid> --cwd "$PWD"` and is marked with `coffer-memory`, so Coffer can find and remove exactly its own entry. Installing twice leaves one entry; removing takes out only Coffer's entry and leaves every other hook and setting untouched. The hook lives in the agent's settings, not in its memory files.

At every start the daemon checks installed hooks and rewrites any whose command is out of date for the running build. It never adds a hook to an agent that does not have one.

### What the agent receives

The composed context contains, in order:

1. the `global` partition's index — what is known about you,
2. the whole index of the partition for the repository the session is in, and
3. the absolute path of that partition's `notes/` folder, with the instruction that a note's body is read as a file.

To see exactly what an agent gets, run the same command the hook runs:

```sh
coffer memory context --agent-uid <uid> --cwd ~/src/payments-api
```

`coffer resource show agent <name>` prints an agent's uid. The payload is the same for every agent; the uid only records which agent's hook fired.

The payload is capped at 12,000 tokens by default (`--ceiling-tokens` overrides it). When the index does not fit, the oldest lines are dropped first, the current repository's lines are kept in preference to `global`'s, and the text says how many lines were dropped and which folder still holds them — every note stays readable as a file.

Every time a hook fires, Coffer records an audit event. The agent's **Memory** tab shows only whether the hook is installed; to see whether it is firing, look on the [Activity](/guides/activity) page or run:

```sh
coffer audit list --event-type memory_delivery_fired
```

### In channel turns

A turn that comes from a [channel](/guides/channels) runs no session-start hook, so Coffer puts the same payload — the `global` index, the index of the partition for the conversation's working directory, and where the notes are — into that turn's system prompt instead. Nothing needs installing for this. It stops on the next turn after you switch the `memory` feature off, and a turn gets no memory header at all when the index is empty.

A turn you send from the [Chat](/guides/chat) page does not get this append: it gets memory the way a terminal session does, through the agent's own session-start hook when delivery is installed. No turn gets memory both ways.

### On demand: `coffer__recall`

For a note from a different repository than the one the session is in, an agent calls `coffer__recall` with a word or phrase. It searches every enabled partition with a literal, case-insensitive match and returns each matching note's absolute path, title and one-line description — never the body, which the agent then reads as a file. Retired notes and `.raw/` are never returned. Recall calls no model.

There is no tool for an agent to write memory through Coffer. An agent records something the way it always does, in its own memory, and Coffer reads it on the next pass. The `coffer-guide` skill tells agents this.

## Browse memory

### Coffer's partitions

::: code-group

```sh [CLI]
coffer memory partitions
coffer memory notes payments-api
coffer memory note payments-api retry-budget-for-ledger-writes
coffer memory retired payments-api
coffer memory ls payments-api
coffer memory read payments-api MEMORY.md
```

```text [Web UI]
Memory → choose the partition
```

:::

The **Memory** page lists partitions with their repository, number of notes and status. A partition whose repository no longer exists on disk is marked **Repository missing**; nothing is delivered from it, and it stays listed until you delete it.

A partition's page shows its folder as a file tree — `MEMORY.md`, `notes/`, `RETIRED.md` and `.raw/` (marked **Derived input**) — beside a read-only preview with **Open in editor** and **Reveal in Finder**. There are no per-note edit or delete actions: the notes are derived, and the next distil pass would rewrite an edit.

`coffer memory note` prints a note together with the entries behind it and the absolute path of each native file they were read from, so you can trace a note that reads wrong back to what the agent actually recorded.

### An agent's own memory

To see the memory an agent keeps for itself, open **Agents → choose the agent → Memory tab**. The **Agent's own (not via Coffer)** table lists each of the agent's native memory stores by project, path and number of items. Choose one to browse its files read-only. The agent owns and rewrites these files; open one in your editor if you want to change it. Changes you make there reach Coffer's notes on the next aggregation and distil.

## Enable or disable a partition

A partition has one switch. Every enabled partition is served to every agent — including agents that contributed nothing to it, which is the point of aggregating. A disabled partition is left out of session-start delivery and out of `coffer__recall`.

::: code-group

```sh [CLI]
coffer resource disable memory payments-api
coffer resource enable memory payments-api
```

```text [Web UI]
Memory → the Status control on the partition's row
```

:::

Disabling controls what Coffer hands to agents. It does not make the files unreadable: they are ordinary files under `~/.coffer/memory/`.

To stop Coffer reading one agent's memory at all, disable that agent (see [Agents](/guides/agents)). To stop memory entirely, switch the `memory` feature off.

## Rebuild a partition

Because everything under `~/.coffer/memory/` is derived, you can throw a partition away and build it again from the agents' own memory:

```sh
rm -rf ~/.coffer/memory/payments-api
coffer memory sync
coffer memory distil payments-api
```

The rebuilt partition covers the same subjects from the same sources. Its wording will differ, because notes are a distillation, not a copy. Retirements recorded in the deleted `RETIRED.md` are lost with it, so a subject that was retired may come back.

To remove a partition from Coffer entirely — for example one marked **Repository missing** — delete its resource:

```sh
coffer resource delete memory payments-api
```

## Troubleshooting

**A partition is empty or missing.** Check that the agent is registered and enabled, then run `coffer memory sync` and read its report. Entries learned outside a git repository do not get a partition of their own.

**An agent is not given its memory at session start.** Run `coffer memory delivery` to confirm the hook is installed for that agent, then `coffer audit list --event-type memory_delivery_fired` to see whether it fires. Run `coffer memory context --agent-uid <uid> --cwd <repo>` to see what would be delivered.

**Notes read like copies of the source, one per entry.** Coffer's model is not configured, so distil is running mechanically. Configure it under **Settings → Coffer's model**, then run `coffer memory distil <partition>`.

**`coffer__recall` is missing from the agent's tools.** The `memory` feature is switched off on this machine, or Coffer's MCP server is not installed for that agent (`coffer agent mcp install <agent>`).

## Related

- [Knowledge](/guides/knowledge)
- [Skills](/guides/skills) — the `coffer-guide` skill tells agents how memory works
- [Agents](/guides/agents)
- [Experimental features](/guides/experimental-features)
- [Memory architecture](/architecture/memory)
- [MCP tools reference](/reference/mcp-tools)
- [Memory spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/memory/spec.md)
- [Aggregate the agents' memory; never write it](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/aggregate-agent-memory-never-write-it.md)
