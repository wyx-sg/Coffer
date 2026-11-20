---
title: Memory
description: One memory for every agent you use. Agents write what they learn about you and your projects into Markdown files in your vault, and Coffer hands each new session its project's memories.
---

# Memory

Coffer keeps one memory for every coding agent you use. It is a folder of Markdown files in your vault, one folder per project and one file per topic. Your agents write the files themselves while they work, following rules Coffer gives them in its `coffer-guide` skill. When a session starts in a repository, Coffer hands it that project's memories. [Vault sync](/guides/vault-sync) carries the files to your other machines, so what Claude Code learned on your laptop this morning, Codex knows on your desktop this afternoon.

Memory is an [experimental feature](/guides/experimental-features): switch it on in **Settings → Features** first.

## How it works

1. **An agent writes.** When you tell an agent about yourself or how you want it to work, correct it, or tell it a fact about the project the repository does not hold, the agent adds a line to the fitting topic file in the project's memory folder, using its own file tools. There is no Coffer tool for memory.
2. **Coffer hands it over.** At the start of every session in a repository, a hook Coffer adds to each agent prints that project's memories into the session (up to about 4 KB). What does not fit is listed by path and title, and the agent reads a file when it is relevant. Sessions Coffer runs itself (Conversations, [channels](/guides/channels), [scheduled tasks](/guides/scheduled-tasks)) carry the same text in their system prompt instead.
3. **An agent tidies.** Lines pile up. **Tidy** on the Memory page hands an agent a prompt to merge, split and prune the files, and the whole tidy is recorded as one change you can undo.

Coffer never reads or writes an agent's own memory (Claude Code's auto memory, Codex's memories). Each agent's own memory keeps working beside Coffer's; see [Your agents' own memory](#your-agents-own-memory).

## Memory, knowledge or a skill

Memory is about you; [knowledge](/guides/knowledge) is about the world. Ask, in order:

1. Would it still hold for someone else? If not, it is **memory**: who you are, how you like to work (preferences, corrections, what you approve), a project's current state and decisions the repository does not record.
2. Is it about an outside system, team or process, or does it need a source? Then it is **knowledge**: how a service or a team works, its pitfalls, an imported document, anything that goes stale or is worth sharing.
3. Is it a fixed sequence of steps you repeat? Then it is a **[skill](/guides/skills)**.

What the repository already says, one-off requests and secrets belong nowhere.

| | Memory | Knowledge |
| --- | --- | --- |
| Holds | you, how to work with you, a project's state | outside systems, teams, processes and their pitfalls |
| Written by | your agents, as they learn | you, or an agent writing it down |
| Organised by | project, one file per topic | collection |
| Format | fixed by Coffer | each collection's own |
| Reaches an agent | handed to every session at start | the agent reads it when the `coffer-guide` skill points there |
| Stored | `vault/memory/`, synced like other vault content | the vault, synced like other vault content |

## The hub {#the-hub}

```text
~/.coffer/vault/memory/projects/
└── github.com-acme-payments/      one folder per project
    ├── testing.md                 one topic per file
    └── release.md
```

A project is a git repository. Its folder is named after the repository's `origin` URL with every character other than a letter, a digit, `.`, `_` or `-` turned into `-`, so two clones on two machines share one folder. A repository with no remote uses its folder's name. A session outside any repository is handed no memories.

Each file is one topic: memories that belong together and are used together.

```markdown
---
title: Testing
type: feedback
updated: 2026-11-19
---
Run only the failing tests while fixing them; the whole suite only before a push.
Never mock the vault in integration tests: a mocked vault once hid a broken migration.
```

| Field | Meaning |
| --- | --- |
| `title` | the topic in a few words |
| `type` | `user` (who you are), `feedback` (how you want an agent to work) or `project` (a project's state the repository does not record) |
| `updated` | the day the file last changed |
| body | one memory per line, at most 400 characters |

The format and the rules are Coffer's and the same for every agent, so the hook, the Memory page and every agent read the files the same way. You do not edit the rules. A file that breaks the format is still read and handed over; the Memory page names what is wrong, and the next tidy fixes it.

## What a session is handed

At session start the hook prints a block like this into the session:

```text
<coffer-memory project="github.com/acme/payments">
Your memories of this project, kept by Coffer in ~/.coffer/vault/memory/projects/github.com-acme-payments/ …

## Testing (feedback, updated 2026-11-19)
Run only the failing tests while fixing them; …

Not shown here; read a file when it is relevant:
- ~/.coffer/vault/memory/projects/github.com-acme-payments/release.md: Release
</coffer-memory>
```

Memories about you come first, then how to work with you, then the project's state, newest first within each. The block stays within about 4 KB.

### The hook in each agent

While memory is on, Coffer keeps one `SessionStart` hook in each registered agent that runs `coffer memory session-start`:

| Agent | Where |
| --- | --- |
| Claude Code | `hooks.SessionStart` in `~/.claude/settings.json` |
| Codex | `hooks.SessionStart` in `~/.codex/hooks.json` |

Coffer adds its hook beside any hooks of your own and removes only its own. It updates the hook when the `coffer` command moves, and removes it when you switch memory off or remove the agent. Each change is in the [audit log](/guides/activity) as `memory_hook_installed` or `memory_hook_removed`.

**Codex asks you to review a new hook once** before it runs it: open `/hooks` in the CLI, or **Settings → Hooks** in the Codex app, and approve Coffer's.

An agent with no session-start hook is handed its memories only in sessions Coffer runs itself.

## Letting agents write the files

The memory folder is outside the repository the agent works in, so the agent may ask for permission each time, or its sandbox may block the write. Allow it once:

- **Claude Code**: add an `Edit` rule for the folder to `permissions.allow` in `~/.claude/settings.json`:

  ```json
  { "permissions": { "allow": ["Edit(~/.coffer/vault/memory/projects/**)"] } }
  ```

- **Codex**: add the folder's absolute path to `writable_roots` in `~/.codex/config.toml`:

  ```toml
  [sandbox_workspace_write]
  writable_roots = ["/Users/you/.coffer/vault/memory/projects"]
  ```

An agent that is blocked says so and tells you this, from the `coffer-guide` skill.

## Your agents' own memory {#your-agents-own-memory}

Claude Code and Codex each have a memory of their own. Coffer does not read it, write it or switch it off, and the two do not sync. Whether to keep an agent's own memory on is your choice:

- **Keep it on** and an agent may write some lessons into its own memory and some into Coffer's. Only Coffer's reach your other agents and machines.
- **Switch it off** to have everything in one place. In Claude Code, set `"autoMemoryEnabled": false` in `~/.claude/settings.json` (or toggle it in `/memory`). In Codex, memories are off unless you turned them on (`[features] memories` in `~/.codex/config.toml`, or **Settings → Personalization** in the app).

## The Memory page {#the-memory-page}

**Memory** in the sidebar lists the projects that hold memories, with the number of files in each and how many break the format. Choose a project to see its topic files: title, type and when each was last updated, with a search and a filter by type. Choose a file to read it in a drawer, with what breaks the format named at the top.

- **Edit** opens the whole file, frontmatter included, and saves it as one change. If an agent changed the file meanwhile, the save is refused and you reload it.
- **Delete** removes the file. You can bring it back from History.
- **History** (in **⋯**) lists every change to memory, by an agent, by you or by a tidy, and restores any earlier version.

The page header says where the files are kept.

## Tidying {#tidying}

**Tidy** hands a prompt to an agent of your choice. The agent runs `coffer memory tidy-start`, goes through the projects one at a time, merges topics that belong together, splits a topic that mixes subjects, drops lines that are duplicated, stale or contradicted, moves a line about an outside system into knowledge, fixes every file that breaks the format, and finishes with `coffer memory tidy-finish` and a short report.

While a tidy is open the page says so, and the agent's edits are held together: when it finishes they are committed as one change carrying its report, so History shows the tidy as one entry you can undo at once. A tidy left idle for 30 minutes, or interrupted by a daemon restart, is closed and what it had changed is committed.

**Set up periodic tidy…** (in **⋯**, when [scheduled tasks](/guides/scheduled-tasks) are on) opens a new scheduled task with the Tidy prompt, weekly by default. Change the schedule, agent or prompt before saving. Coffer has no tidy timer of its own.

## On the command line

[`coffer memory`](/reference/cli/memory) lists the projects (`state`), a project's topic files and their problems (`topics`), and one file (`show`); `tidy-start` and `tidy-finish` open and close a tidy; `session-start` is what the hook runs. Editing a file is editing a file: use any editor.

## Upgrading from memory sync

Earlier builds synced memory into each agent's own memory. On the first start of this build Coffer removes what it wrote into your agents: its block in each Claude Code `MEMORY.md` (and a file left empty by that), its `coffer_*.md` files, and its folder in each Codex memory folder. Your agents' own memories are untouched. The entries an earlier build published to the hub, one file per memory, are rewritten in place as topic files; a tidy then merges them into topics.

## Turning memory off {#turning-memory-off}

Switching **Memory** off in **Settings → Features** removes Coffer's hook from every agent, takes the Memory page and its API away, and leaves the memory rules out of `coffer-guide`. The files stay in your vault, and switching memory back on restores the hook.

## Troubleshooting

**A session was not handed its memories.** Check that memory is on, that the agent is registered, and that the session started inside a git repository. In Codex, approve Coffer's hook under `/hooks`. Run `coffer memory session-start` with `{"cwd": "<the repository>"}` on standard input to see what a session there is handed.

**An agent does not write memories.** Check that the `coffer-guide` skill reaches the agent (the agent's **Skills** tab), and that writes to the memory folder are allowed (see [Letting agents write the files](#letting-agents-write-the-files)). You can also tell the agent "remember this".

**A file shows a format problem.** Run Tidy, or edit the file on the Memory page.

**Two machines edited the same file.** Topic files sync like any vault file. Lines appended on two machines usually merge on their own; a real conflict stops [vault sync](/guides/vault-sync) for you to resolve, as any conflict does.

## Related

- [Knowledge](/guides/knowledge)
- [Agents](/guides/agents)
- [Vault sync](/guides/vault-sync)
- [Scheduled tasks](/guides/scheduled-tasks)
- [Memory architecture](/architecture/memory)
- [`coffer memory`](/reference/cli/memory)
- [Memory spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/memory/spec.md)
- [Keep memory in one place in the vault, written by the agents themselves](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/keep-memory-in-one-place-agents-write-themselves.md)
