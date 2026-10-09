# Data Model — Memory

The memory layer's state is files: a hub of entries in the vault, the copies
Coffer writes into each agent's own memory, and one machine-local ledger of
what it wrote. This document describes what is on disk and the records the
surfaces answer with. Authority is [`spec.md`](spec.md) and
[Sync Memory Into Each Agent's Own Memory](../../../docs/decisions/sync-memory-into-each-agents-own-memory.md).

## There is no memory table and no memory kind

**This layer adds no table of its own and no resource kind** ("Add no table or
resource kind"). The hub is files in the vault repository; what this machine
wrote into its agents is `~/.coffer/local/memory-sync.json`. The switch and
interval of the sync are the `memory_sync` pass of the internal-engine
settings document (spec internal-engine).

## The hub

```text
~/.coffer/vault/memory/
├── global/                          # memories about the person
│   └── <id>.md
└── projects/
    └── github.com-acme-payments/    # one folder per project key
        └── <id>.md
```

The hub is in the vault, so vault sync carries it to every machine. Each
entry is one Markdown file with this frontmatter, then the memory's body:

```yaml
---
id: 3f2a91c4de55b071
origin: {machine: <machine id>, agent: claude_code, source: projects/<slug>/memory/feedback_testing}
project: github.com/acme/payments      # absent for global
type: feedback                         # user | feedback | project | reference
title: Integration tests hit a real database
description: Never mock the DB in integration tests; a mocked run hid a broken migration.
search_terms: [migration, integration test]   # when the source states them
created_at: 2026-10-09T06:00:00Z
updated_at: 2026-10-09T06:00:00Z
---
```

| Field | Meaning |
|---|---|
| `id` | `sha256(machine, agent, source)[:16]`: an unchanged source re-read maps to the same entry, so an edit is an update |
| `origin` | the one machine and agent that may change or delete the entry ("Publish only what the origin agent wrote, and only from its machine") |
| `project` | the project key: the normalised remote of the repository, or its directory name when it has none; absent for global |
| `type` | the agent's own memory type; Codex sections map onto `user` and `project` |
| `body` | stored portably: the repository root is `<repo>` and the home directory `~` ("Store paths in a memory portably") |

- The project folder name is the key with every character outside
  `[A-Za-z0-9._-]` turned into `-`; the key itself is in each entry, so the
  folder name is never decoded.
- A sync's hub changes are one vault commit by the writer `memory-sync`.
- An entry whose text the bundled plaintext detector flags is withheld and
  never written to the hub.

## Copies in the agents

What a sync writes into each agent on this machine. A project's memories are
written only where the project is checked out here, with `<repo>` and `~`
expanded to this machine's paths. An agent never receives its own memories
back from its own machine.

| Agent | Project memories | Global memories |
|---|---|---|
| Claude Code | `<config_dir>/projects/<slug>/memory/coffer_<title-slug>.md`, plus a block in that folder's `MEMORY.md` between `<!-- coffer:memory-sync:begin -->` and `<!-- coffer:memory-sync:end -->` (newest first, at most 30 lines, the rest counted) | `<config_dir>/rules/coffer-memory.md`, at most 25 KB |
| Codex | `<config_dir>/memories/extensions/coffer/resources/<id>-<title-slug>.md`, with `instructions.md` beside them | the same folder |

A Claude Code copy carries `coffer: {entry, from, synced_at}` in its
frontmatter; readers skip every file named `coffer_*` that carries it, the
marked block, the rules file, everything under Codex's `extensions/`, and any
Codex bullet tagged `[via Coffer]` ("Never republish Coffer's own copies").
Codex writes nothing while its `memories` feature is off.

## The ledger

`~/.coffer/local/memory-sync.json`, machine-local and never synced:

```json
{
  "version": 1,
  "previewed": true,
  "codex_imports_claude": null,
  "sources": {"<native path>": {"digest": "…", "entries": ["<id>"]}},
  "copies": {
    "claude_code@<config dir>": {"<path>": {"path": "…", "entry": "<id>", "entry_updated_at": "…", "digest": "…", "state": "written"}}
  },
  "delivered": {"claude_code": ["<sentence sha1>"]},
  "last_synced_at": "…",
  "last_report": {}
}
```

| Field | Meaning |
|---|---|
| `previewed` | whether this machine's first preview was written; until then every sync waits as a preview |
| `codex_imports_claude` | the person's answer to "Codex imports Claude Code's memories itself"; `true` skips the Claude Code → Codex direction |
| `sources` | each native source as last read, and the hub entries it produced |
| `copies` | each copy written, per agent (keyed by type and config directory, so two Claude Code directories stay apart); `state` is `written`, `edited` (its digest changed: the agent owns it now) or `removed` (gone: not written again until the entry changes) |
| `delivered` | normalised sentence fingerprints of everything delivered to each agent, so an agent's rewording of a copy is not published back ("an absorbed copy does not circulate") |
| `last_report` | what the last sync read, published, wrote, held back and withheld |

`~/.coffer/local/memory-sync-preview.json` holds a pending preview: the copy
changes a first or large sync (more than 50 copies) would make. **Write**
applies exactly that plan; **Cancel** drops it; a newer sync replaces it.
Losing the ledger costs one preview, never an agent's own memory: every
existing `coffer_` file is recognised by its `coffer.entry`.

## Undo

**Undo sync** removes every copy in `copies` whose state is `written` and whose
file still matches its digest, Claude Code's marked block and rules file, and
Codex's `extensions/coffer/` folder, then turns the `memory_sync` pass off. Edited and removed copies, every agent's own
memory and the hub stay.

## Audit events

| Event | When | Actor |
|---|---|---|
| `memory_synced` | a sync changed the hub or a copy | the person, or `system:memory-sync-worker` |
| `memory_sync_undone` | Undo sync | the person |
| `memory_curation_requested` | Curate now | the person |
| `memory_hook_removed` | the upgrade took the retired hook out of one agent | `system:upgrade` |
