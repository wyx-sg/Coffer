---
title: Memory
description: Let Coffer read what each of your agents has learned, distil it into one set of notes per repository, and hand the right notes back at session start and at each prompt. You can read and edit the notes too.
---

# Memory

Coffer reads the memory your agents already keep — Claude Code's per-project notes, Codex's task groups and profile — distils it into one set of notes per repository plus one global set, and makes those notes available to every agent. It never writes back into an agent's own memory. This page covers what Coffer reads, where the notes live, how agents receive them, how to see delivery working, and how to browse, edit, switch off and rebuild the notes.

## What memory aggregation is for

Every agent keeps its own memory, and none can see another's. What Claude Code learned about a repository this morning, Codex has to be taught again this afternoon.

Coffer closes that gap without taking over either agent's memory:

1. **Read.** Coffer reads each registered, enabled agent's native memory files. It never creates, changes, moves or deletes anything there, and never changes an agent's memory settings.
2. **Distil.** Coffer's own model turns what it read into notes in Coffer's own words — one topic per file — merging lessons that two agents learned separately into one note.
3. **Deliver.** An installed hook hands the notes back at two moments: the index for the repository and `global` at session start, and the few notes a prompt names when you send it.

Memory is not [knowledge](/guides/knowledge). Knowledge is what you or an agent deliberately wrote down about the world; memory is what agents learned while working, collected automatically.

| | Memory | Knowledge |
| --- | --- | --- |
| Comes from | agents' own memory files, read-only | you, or an agent writing it down |
| Organised by | repository, plus `global` | collection |
| Who writes the stored text | Coffer, distilling | you and agents, directly |
| Reaches an agent | through a hook: the index at session start, matching notes at each prompt | the agent reads it when the `coffer-guide` skill points there |
| If the store is lost | rebuilt from the agents' own memory | gone |

## What Coffer reads

| Agent | Files read |
| --- | --- |
| Claude Code | Each fact file in `<config_dir>/projects/<project>/memory/*.md` — its frontmatter `name`, `description` and `type`, and its body. Claude Code's own `MEMORY.md` index is skipped. |
| Codex | `<config_dir>/memories/MEMORY.md` — each task group's preferences, reusable knowledge and failures — and `memory_summary.md` — the profile, standing preferences, and the search terms Codex lists for each task group. |

Coffer does not read session transcripts or rollout files. Both agents already distil their own sessions into memory, and Coffer starts from that.

If an agent's memory format changes and a file can no longer be parsed, that agent contributes nothing to the pass, the failure is reported with the file's path and the reason, the other agent's memory is still read, and notes from earlier passes are left in place.

## Partitions

A **partition** is a folder under `~/.coffer/derived/memory/`. There is one per repository, plus one named `global`:

- An entry is filed under the repository it was learned in. The main checkout, its worktrees and another clone of the same repository all map to one partition, named after the repository's directory.
- An entry about **you** rather than a project (type `user`: your preferences, Codex's profile) is filed under `global`, whichever repository it came from.
- Guidance on how to work (type `feedback`) is filed with the repository it was given in, because it usually binds that repository. Only feedback given outside any repository goes to `global`.
- An entry learned in a directory that is not a repository creates no partition. The distil pass decides whether it belongs in `global` or nowhere.

Partitions are created by aggregation only; you do not create them.

```text
~/.coffer/derived/memory/
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
| `RETIRED.md` | Each retired note's title, the reason, and the note that replaced it. The next pass reads this file so a retired subject is not brought back from the same unchanged source. A note is also retired here, with the reason "its sources are gone", when every raw entry it was built from has left `.raw/` — the agent deleted the fact, or it is now filed into another partition — and that kind of record does not stop the subject coming back. |
| `.raw/` | Every entry exactly as it was read, with the agent, source path and read time. It is the distil pass's input and lets you check a note against the words it came from. It is not shown in the web UI; open it on disk, under `~/.coffer/derived/memory/<partition>/.raw/`. |

Everything under `~/.coffer/derived/memory/` is derived. It can be deleted and rebuilt at any time, and it is not carried by [vault sync](/guides/vault-sync): each machine builds its own from the agents installed on it.

## How the passes run

Two background passes keep the partitions current. Both are on by default.

| Pass | What it does | Default schedule | Uses a model |
| --- | --- | --- | --- |
| **Read from agents** (aggregation) | Reads every enabled agent's memory files and writes new entries into `.raw/`. A source file whose content has not changed since the last pass is skipped. | At daemon start, then hourly | No |
| **Distil memory** | For each partition, routes new entries against the index — merge into a note, open a new note, retire a note, or keep nothing — then rewrites only the notes that changed, and rewrites `MEMORY.md`. | About a minute after start, then every 6 hours | Yes, when configured |

The two passes run on separate timers: distil does not wait for an aggregation (to run both at once, use [Update memory](#run-a-pass-now)), and a partition with no new entries since its last distil costs no model call. Distil is incremental: the routing request carries the new entries and the index lines, never the note bodies, and each touched note is rewritten in its own small request. Two agents' entries about the same lesson, however differently worded, end up in one note whose `origins` name both. When a new entry disagrees with a note, the [newer statement wins unless the older one is shown to be right](#when-two-statements-disagree).

**Without an internal model.** If Coffer's model is not configured (see [Model providers](/guides/providers)), distil still runs, mechanically: each entry becomes a note of its own and `MEMORY.md` is written from their frontmatter. You get a thinner index, not an empty one, and no model is called.

::: info What leaves your machine
Only the distil pass sends memory content anywhere, and only to the model endpoint you configured. Aggregation and delivery send nothing; prompt-time ranking runs inside the daemon.
:::

### Change the schedule

In the Memory header, **Automatic · hourly** opens a popover with one switch, **Read memory automatically**, and an interval. The switch turns aggregation and distil on or off together; the interval is how often the agents' memory is read, and distil keeps its own slower interval. The popover also says when the memory was last read and when the next read is due. The header shows when the agents' memory was last read (*Read 14 min ago*), and says so when an agent's memory could not be read: a warning banner then names the agent and the path, with **Retry** and **Ask an agent ▾**, whose prompt asks an agent to fix the read permission; while **Update memory** runs it reads *Distilling 2 of 5 partitions*.

A change applies without a restart. The popover offers 15 minutes to 1 day; the settings API accepts down to 60 seconds.

### Run a pass now

```text
Memory → Update memory
Memory → choose the partition → Update memory
```

**Update memory** runs both passes in one action: it reads every registered agent's latest memory, then distils every partition that gained new entries. It reports how many entries it read across how many partitions, any sources that failed to parse, and which partitions it distilled. A partition whose distil pass is already running is reported as skipped rather than failing the update. The button is the same on the partitions page and on a partition's page. Only one distil pass runs per partition at a time. `coffer daemon status` shows what is running now.

## How agents receive memory

Memory reaches a session at two moments:

| Moment | What the agent gets | Hook event |
| --- | --- | --- |
| **Session start** | the index of `global` and of the repository the session is in, and where the notes are | `SessionStart` |
| **Each prompt you send** | up to three notes your prompt names, if any match well enough | `UserPromptSubmit` |

Both go through one hook, installed into the agent's own settings when you connect the agent to Coffer. The decision behind this design, and the evidence for it, is the ADR [Memory Reaches a Session at Two Moments](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md).

### Install the hook

Delivery goes through each agent's own hook mechanism. The hook is one part of the agent's [Coffer connection](/guides/agents#connect-an-agent-to-coffer): connecting an agent installs it and disconnecting removes it. Coffer never installs it into an agent you have not connected.

```text
Agents → choose the agent → Connect
```

What gets installed is two entries, one per event, in the agent's settings file: `~/.claude/settings.json` for Claude Code, `~/.codex/hooks.json` for Codex.

| Event | When it fires | Timeout |
| --- | --- | --- |
| `SessionStart` | on startup, resume, clear and compact | 10 seconds |
| `UserPromptSubmit` | each prompt you send | 5 seconds |

Both entries run the same command, an internal entry point of `coffer` that you never type yourself. It is called by its full path (usually `~/.coffer/bin/coffer`), because the shell an agent runs hooks in may not have `~/.coffer/bin` on its `PATH`. The command reads the event the agent hands it and answers in the JSON both agents read. Each entry is marked with `coffer-memory`, so Coffer can find and remove exactly its own entries. Installing twice leaves one entry per event, and removing takes out only Coffer's entries and leaves every other hook and setting untouched. The hook lives in the agent's settings, not in its memory files.

::: warning Codex needs you to approve both entries
Codex runs a hook only after you have approved it, and it skips an unapproved one without saying so. After connecting a Codex agent, and again after any Coffer update that changes the hook's command, open Codex, run `/hooks` and trust each of Coffer's two entries: `SessionStart` and `UserPromptSubmit`. An entry you leave unapproved is simply skipped, so trusting only `SessionStart` gives you the index and nothing else. Coffer does not approve its own hook; it only reports it as untrusted. The agent's **Hooks** tab and the attention list all show when an approval is missing.
:::

The daemon keeps installed hooks current. On every reconcile pass it rewrites any hook whose command or set of events is out of date for the running build, back into the two current entries. It never adds a hook to an agent that does not have one.

Whether the hook is installed, current and trusted is shown on the **agent's** page (its connection status and **Hooks** tab), not with memory. The delivery views in [See it working](#see-it-working) report what was delivered, never the state of a hook.

### At session start: the index

The session-start context contains, in order:

1. the `global` partition's index — what is known about you,
2. the index of the partition for the repository the session is in,
3. the absolute path of that partition's `notes/` folder, with the instruction that a note's body is read as a file, and
4. the memory root (`~/.coffer/derived/memory/`), which spans every partition, so a note from another repository is one search away with the agent's own tools. The `coffer-guide` skill names the knowledge root too, so an agent knows where both live.

What a hook prints is capped at 9,500 bytes, which is under both agents' limits for a hook's output: Claude Code shows the model only a short preview of anything past about 10,000 characters, and Codex cuts the middle out of anything past about 2,500 tokens. A large vault's index is bigger than that. When the index does not fit, the oldest lines are dropped first, the current repository's lines are kept in preference to `global`'s, and the text says how many lines were dropped and which folder still holds them — every note stays readable as a file.

### At each prompt: the notes your prompt names

When you send a prompt, Coffer ranks the notes of the current repository's partition and of `global` against it, matching words in each note's title, description, search terms and body. Chinese text is matched too. The best **three** notes that clear a relevance bar are added to the session, each as its file path and one line:

```text
Coffer memory: notes recorded for this user that may apply to this request. …
- (/Users/you/.coffer/derived/memory/payments-api/notes/retry-budget-for-ledger-writes.md) a fact they recorded: Retry budget for ledger writes — ledger writes retry three times, then park in the dead-letter table.
```

- A note is given **once per session**. A later prompt that names the same note does not bring it in again, even after the daemon restarts.
- A short prompt — under three words — and a nudge such as `continue`, `ok` or `继续` bring in nothing, so a conversation that is just moving along costs nothing.
- The whole addition stays under 1.5 KB.
- The ranking is plain word matching over the note files. Nothing is embedded, and nothing leaves your machine.

### In channel turns

Coffer drives a turn that comes from a [channel](/guides/channels) itself, so it delivers that turn's index and notes itself. On an agent connected to Coffer, the agent still runs Coffer's hook inside the turn, and the hook stands aside for session start and each prompt, so nothing arrives twice:

- **The index.** The session-start payload — the `global` index, the index of the partition for the conversation's working directory, and where the notes are — goes into that turn's system prompt. A turn gets no memory header at all when the index is empty.
- **The notes your message names.** Coffer ranks each message you send against the notes exactly as it does [at each prompt](#at-each-prompt-the-notes-your-prompt-names) — the same three-note limit, relevance bar and size cap — and adds what it finds after your message in what the agent receives. A note is given once per conversation, and each delivery is recorded in the audit log as a `prompt` fire of the agent. Your message is stored in the conversation as you wrote it.

Nothing needs installing for this. On a connected agent, Coffer's hook still runs inside a channel turn and stands aside for both moments, so the agent never receives memory twice.

A turn you send from the [Conversations](/guides/chat) page does not get this append: it gets memory the way a terminal session does, through the agent's own hook when the agent is connected to Coffer. No turn gets memory both ways.

### On demand: search the memory root

For a note from a different repository than the one the session is in, an agent searches the memory root with its own file tools — `grep` over `~/.coffer/derived/memory/` covers every partition at once, and the session-start payload names that root. Every note is a Markdown file with its title and one-line description in its frontmatter. There is no memory tool: Coffer exposes nothing for an agent to call.

There is no tool for an agent to write memory through Coffer either. An agent records something the way it always does, in its own memory, and Coffer reads it on the next pass. The `coffer-guide` skill tells agents this.

## See it working

**What memory delivered this week.** For every agent with the hook, over the last seven days: how many times memory reached it, when it last did, and how many distinct notes its sessions actually opened.

```text
Memory → Delivered at session start
```

On the **Memory** page, the **Delivered at session start · Last 7 days** block has one row per agent: *Delivered 42 times in the last 7 days · 17 memories read · last 12 min ago*. An agent that received nothing in that time reads **Not delivered in the last 7 days**. The block never shows the hook itself; its state and **Repair** are on the agent's page.

"Notes read" is counted from the file paths the agent's tool calls opened under the memory root; Coffer never reads what a message or a tool result said. It reads **unavailable** when Coffer cannot read that agent's transcripts, which is not the same as zero.

**Exactly what an agent is given at session start** in one partition's repository — the same text the hook would print, composed the same way:

```text
Memory → choose the partition → Delivered
```

The partition's **Delivered** tab shows that text read-only, with a switch between the connected agents (Claude Code first), its length in characters and a **Copy** button.

**Every delivery, one by one.** Each delivery is an audit event naming its moment (`session_start` or `prompt`), the session and the notes it carried, never their text:

```sh
coffer log audit --event-type memory_delivery_fired --limit 20
```

You can read the same events on the [Activity](/guides/activity) page.

## Browse and edit memory

### Coffer's partitions

```text
Memory → choose the partition
```

In the web UI a note is called a **memory** (中文 记忆条目): one memory per subject. The **Memory** page carries the **Experimental** tag beside its title; its primary action is **Update memory**, with **Automatic · hourly** beside it. It lists partitions in a table — the partition, its path (**Every project** for `global`), a **Sample memory** (the most recently updated one, or how many entries are waiting to be distilled), its number of memories, its **Sources** (the agents it was learned from) and a **Distilled** column saying when it was last distilled — under the **Delivered at session start** block. Healthy rows are grey; only **Repository missing** is coloured. With no partition yet it shows the first-run welcome **Nothing distilled yet** instead: **Update memory** and the connected agents whose memory Coffer found on this Mac, or, with no agent connected, **Open Agents** to connect one. A partition whose repository no longer exists on disk is marked **Repository missing**; nothing is delivered from it, and it stays listed until you delete it (see [Rebuild a partition](#rebuild-a-partition)).

A partition's page has no back link and no Experimental tag: its title is the partition's name, and the line under it carries the path, the number of memories and when it was last distilled. It has two tabs:

- **Memories** (the default) lists the partition's memories — each by its title and one-line description — beside the selected one. The selected memory shows its title, a line naming the agents it was learned from and when it was last updated (*Learned by Claude Code, Codex · updated …*), and its body, with **Edit**, **Open in editor** and **Reveal in Finder**; the list and the memory fill the window and scroll inside. Under the list, a collapsed **Retired** group lists, read-only, the memories that were retired and the reason for each. While Coffer's engine is not set, a banner explains that each agent's entry stays its own memory until it is set in **Settings › General**, with **Open Settings**. A partition not yet distilled shows no list, only an empty state.
- **Delivered** shows the session-start text each agent receives in this partition's project (see [See it working](#see-it-working)).

The page shows Coffer's memories only. It shows no file tree, no `MEMORY.md` or `RETIRED.md`, no `.raw/`, no native paths and no agent's original text; those stay on disk. A memory is not deleted from the page: it is derived, and distil retires one when its sources are gone. The header's **⋯** menu offers **Reveal partition folder**, **Copy path**, **Distil history in Activity** (the Changes tab, where every distil pass is recorded) and, only while the repository is missing, **Delete partition…**.

A note's `origins` frontmatter names every agent file it was built from, and `.raw/` holds each entry exactly as it was read, so you can trace a note that reads wrong back to what the agent actually recorded. On disk, a partition's `MEMORY.md`, `notes/` and `RETIRED.md` are plain files under `~/.coffer/derived/memory/<partition>/`.

### Edit a memory

A memory that is wrong or incomplete can be fixed by you:

- **In the web UI.** Choose the memory in its partition and select **Edit**, change the body, and save. If the note changed in the meantime — a distil pass rewrote it, or you edited the file elsewhere — Coffer does not overwrite it: it shows a conflict prompt with the note as it is now, so nothing you typed or the pass wrote is lost.
- **On disk.** Open the note under `~/.coffer/derived/memory/<partition>/notes/` in your own editor. The next index line and the next session's delivery carry the change.

An edited note stays as you left it until newer evidence revises it. The next distil pass that routes a new entry to that note starts from your edited text, and follows the rule in [When two statements disagree](#when-two-statements-disagree). An entry from last month that carries no evidence does not overwrite what you wrote today.

Because the tree is derived, rebuilding a partition (see [Rebuild a partition](#rebuild-a-partition)) loses every edit: the notes come back from the agents' own memory, in new wording.

### When two statements disagree

When a distil pass finds two statements that disagree — a note and a new entry, or your edit and newer material — the newer statement wins unless the older one is shown to be right by evidence: a source, a date, a command's output or the code. No writer is exempt: a statement is not safe because a person wrote it, and not suspect because an agent did. A superseded statement stays legible: it is retired with the reason and the note that replaced it, or kept in the rewritten body with the date it changed. History and restore remain your way back if a pass gets it wrong.

### An agent's own memory

To see the memory an agent keeps for itself, open **Agents → choose the agent → More → Memory**. The tab opens with **Coffer's memory** for that agent — its memory hook, when it last fired and what it delivers — and below it lists each of the agent's own native memory stores by project, path and number of items. Choose one to browse its files read-only. The agent owns and rewrites these files; open one in your editor if you want to change it. Changes you make there reach Coffer's notes on the next aggregation and distil.

## Every partition reaches every agent

A partition has no on/off switch and no per-agent reach. Every partition is served to every agent — including agents that contributed nothing to it, which is the point of aggregating — through the memory hook.

This controls what Coffer hands to agents, not what they can open: the notes are ordinary files under `~/.coffer/derived/memory/`.

To stop Coffer reading one agent's memory at all, disable that agent (see [Agents](/guides/agents)).

## Rebuild a partition

Because everything under `~/.coffer/derived/memory/` is derived, you can throw a partition away and build it again from the agents' own memory. Delete the partition's folder on disk, then choose **Update memory** in the web UI. The rebuilt partition covers the same subjects from the same sources. Its wording will differ, because notes are a distillation, not a copy, and every edit you made to its notes is gone. Retirements recorded in the deleted `RETIRED.md` are lost with it, so a subject that was retired may come back.

To remove a partition from Coffer entirely — for example one marked **Repository missing** — remove it:

```text
Memory → Delete on the partition's row
Memory → choose the partition → ⋯ → Delete partition…
```

The web UI offers **Delete** only on a partition marked **Repository missing**: any other partition is recreated by the next update. The confirmation says how many distilled memories go with it; the agents' own memory for that folder is not touched.

## Limits

- **Rules about every reply are not memory's job.** A rule such as "always reply in Chinese" or a preferred tone applies to every turn. No prompt names it, so retrieval does not deliver it at the right moment. Put such rules in the instructions the agent loads on every turn: `CLAUDE.md` for Claude Code, `AGENTS.md` for Codex. You own those files, and Coffer never writes them.
- **A tiny store rarely clears the bar.** The relevance bar was tuned on a store of real size. The ranking weighs each word by how rare it is across the whole store, so with only a handful of notes even a matching note scores low, and a prompt usually brings in nothing. That is on purpose: it stops a prompt that shares only common words from bringing in noise. Retrieval starts to work as the agents learn more.
- **A session idle for more than a week is treated as new.** Coffer rebuilds what each session was given from the delivery fires in the audit log, so a daemon restart does not repeat a note. Fires older than seven days are not read back, so a session that has been idle that long can be given a note again.
- **Retrieval reads only the current repository's partition and `global`.** A note filed under another repository is never brought in at a prompt. The agent can still find it by searching the memory root.
- **Memory never gets in the way when Coffer is down.** If the daemon is not running, is slow, or answers with an error, the hook prints nothing and lets the prompt through. You lose that fire's delivery, nothing more. A short prompt never contacts the daemon at all.

## Troubleshooting

**A partition is empty or missing.** Check that the agent is registered and enabled, then choose **Update memory** and read its report. Entries learned outside a git repository do not get a partition of their own.

**An agent is not given its memory.** Open the agent's **Hooks** tab to confirm Coffer's hook is **Current** on both events (press **Repair** if it reads **Out of date** or **Missing**). For Codex, check that both entries are trusted in `/hooks`. Then open **Memory → Delivered at session start** to see whether memory reached the agent this week, and the partition's **Delivered** tab to see exactly what it is given at session start.

**A prompt brings in no notes.** Short prompts and nudges never do. Otherwise the prompt's words did not match any note of this repository or `global` well enough; with only a few notes in the store that is normal (see [Limits](#limits)). A note the session was already given is not given again.

**Notes read like copies of the source, one per entry.** Coffer's model is not configured, so distil is running mechanically. Configure it under **Settings › General → Coffer's model**; entries distilled after that, by **Update memory** or the next sweep, go through the model.

**My edit to a note disappeared.** Either newer evidence revised the note (the Activity page's Changes tab records each distil pass), or the partition was rebuilt, which loses edits.

## Related

- [Knowledge](/guides/knowledge)
- [Skills](/guides/skills) — the `coffer-guide` skill tells agents how memory works
- [Agents](/guides/agents)
- [Memory architecture](/architecture/memory)
- [MCP tools reference](/reference/mcp-tools)
- [Memory spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/memory/spec.md)
- [Aggregate the agents' memory; never write it](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/aggregate-agent-memory-never-write-it.md)
- [Memory reaches a session at two moments](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md)
