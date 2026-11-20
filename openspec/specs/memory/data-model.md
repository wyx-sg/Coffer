# Data Model — Memory

Memory is files: one Markdown file per topic in the vault, which agents write
themselves. This document describes what is on disk, the hook Coffer keeps in
each agent, and the records the surfaces answer with. Authority is
[`spec.md`](spec.md) and
[Keep Memory in One Place, Written by the Agents Themselves](../../../docs/decisions/keep-memory-in-one-place-agents-write-themselves.md).

## There is no memory table and no memory kind

**This layer adds no table of its own and no resource kind** ("Add no table,
resource kind or agent mechanism"). The hub is files in the vault repository;
its history is the vault's git history.

## The hub

```text
~/.coffer/vault/memory/
└── projects/
    └── github.com-acme-payments/    # one folder per project
        ├── testing.md               # one topic per file
        └── release.md
```

The folder is the project key with every character outside `[A-Za-z0-9._-]`
turned into `-`. The key is the repository's normalised `origin` URL
(`github.com/acme/payments`), or the repository folder's name when it has no
remote, so two clones on two machines share one folder.

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
|---|---|
| `title` | the topic in a few words; a file without one is titled by its file name |
| `type` | `user` (who the developer is), `feedback` (how they want an agent to work) or `project` (a project's state the repository does not record) |
| `updated` | the day the file last changed, `YYYY-MM-DD` |
| body | one memory per line, at most 400 characters each |

What breaks the format is named, never fixed by Coffer: `no_title`,
`bad_type`, `no_updated`, `no_memories`, `long_line`.

Every change is a vault commit. An agent's edit is committed by the vault
scanner as a `disk` write; a person's edit or delete on the Memory page is a
`user` write; a tidy is one `agent` write with operation `tidy` whose summary
is the agent's report. An entry an older build published (one memory per file,
with `id` and `origin`) is rewritten in place to this format at daemon start,
as one `daemon` write.

## The hook in each agent

While the memory feature is on, each registered agent whose record names a
place for it carries one hook of Coffer's under its `SessionStart` event:

| Agent | File | Entry |
|---|---|---|
| Claude Code | `<config_dir>/settings.json` | `hooks.SessionStart[].hooks[] = {"type": "command", "command": "<coffer> memory session-start"}` |
| Codex | `<config_dir>/hooks.json` | the same shape |

A hook is Coffer's when its command runs `memory session-start`. Codex runs a
new or changed hook only after the person reviews it once (`/hooks`, or
Settings > Hooks in the app).

## What a session is handed

```text
<coffer-memory project="github.com/acme/payments">
Your memories of this project, kept by Coffer in ~/.coffer/vault/memory/projects/github.com-acme-payments/ …

## Testing (feedback, updated 2026-11-19)
Run only the failing tests while fixing them; …

Not shown here; read a file when it is relevant:
- ~/.coffer/vault/memory/projects/github.com-acme-payments/release.md: Release
</coffer-memory>
```

At most 4 KB. `COFFER_MEMORY_IN_PROMPT=1` in a session's environment means
Coffer already put this text in its system prompt, and the hook prints nothing.

## Records

| Record | Fields |
|---|---|
| `MemoryStateOut` | `folder_path`, `projects[]`, `tidy_running`, `tidy_started_at`, `tidy_handoff.prompt` |
| `MemoryProjectOut` | `folder`, `topics` (files), `problems` (files breaking the format), `updated` (newest) |
| `MemoryTopicOut` | `project`, `name`, `title`, `type`, `updated`, `body`, `problems[]` |
| `MemoryFileOut` | a topic plus `path`, `text` (the whole file) and `digest` (what an edit or delete quotes) |

A tidy is held in the daemon's memory only: while one is open the hub's edits
stay uncommitted, and a restart, or 30 minutes without a change, closes it.

## Audit events

| Event | When | Actor |
|---|---|---|
| `memory_hook_installed` | the reconciler added Coffer's hook to an agent | `system` |
| `memory_hook_removed` | the reconciler removed it (memory off, or the agent removed) | `system` |

The retired events of earlier memory layers (`memory_synced`,
`memory_sync_undone`, and older) stay readable on old rows.
