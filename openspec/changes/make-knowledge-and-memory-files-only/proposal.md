## Why

Agents reach knowledge and memory with the tools they already use all day —
`Read`, `Grep`, `Edit`, `Write` — and almost never with the ones Coffer built
for them. `coffer__write` was called four times in thirty days on the
maintainer's machine, all on one afternoon. People read and edit the same files
in the web UI or in their own editor. The `coffer knowledge` and
`coffer memory` command groups are mostly run by agents through their shell,
and the REST routes behind them exist largely to keep REST and the CLI in
parity, a rule that grows the CLI with every page the web UI gains.

Memory triggers show the cost of a mechanism nobody can reach. Four exist, all
proposed by the distil pass, none ever armed: the web UI has no place to arm
one, so in thirty days memory was delivered 414 times and held a command zero
times. One of the four matches browser tool names against shell commands,
where it can never match what it meant.

And who wrote a statement is the wrong test of whether it is true. Curation
treats an edit made outside a pass as untouchable, but that edit may be an
agent's, may be wrong, and may go stale like anything else.

So knowledge and memory become plain files that agents and people both edit,
plus a web UI for people. Coffer keeps the hook that hands memory to a session
and the passes that keep the files in shape, and judges a statement by when it
was made and the evidence behind it, never by its writer. The CLI keeps only
what something other than the web UI needs.

## What Changes

- knowledge: **BREAKING** `coffer__write` is removed. An agent adds knowledge by
  writing a Markdown file into a collection's `.inbox/`; the sweep treats a new
  inbox file as submitted material, fills any frontmatter it lacks, and audits
  it as `knowledge_written`. Editing a document on disk stays a complete way to
  change knowledge.
- knowledge: **BREAKING** "Let newer statements win and a person's edit stand"
  becomes "Let the newer or better-evidenced statement win": the newer
  statement wins unless the older one is shown to be right, and no writer —
  person, agent or pass — is exempt. An edited document is still carried
  outward to the documents that disagree with it, as a newer statement. A pass
  still never overwrites a file that changed after it read it, and still keeps
  every frontmatter key a rewrite did not set.
- memory: a person can edit a memory in the web UI (the partition page's
  memory gains Edit, with the same changed-on-disk conflict handling the
  knowledge editor has) or in their own editor. An edited note is the note: a
  later distil pass revises it only by the same newer-or-better-evidenced rule.
- memory: **BREAKING** triggers are removed — the `block` and `context` kinds,
  `vault/memory-triggers/`, the distil pass's trigger proposals, the guard and
  error moments, and the `PreToolUse` and `PostToolUse` hook entries. Memory
  reaches a session at two moments: the index at session start and the notes a
  prompt names.
- knowledge, memory: **BREAKING** `coffer knowledge` (all twelve subcommands),
  `coffer memory` (all but the hidden `coffer memory hook`, which the installed
  hook runs), `coffer path knowledge` and `coffer path memory` are removed. The
  session-start payload and the `coffer-guide` skill name both roots.
- knowledge, memory: **BREAKING** the REST routes become the web UI's own. A
  route the web UI does not call is removed — `POST /api/v1/knowledge/material`
  and the five `/api/v1/memory/triggers` routes among them. The rest are not a
  public API and drop out of the REST reference.
- resource-framework: **BREAKING** "Reach every management operation from both
  REST and the CLI" is replaced by "Keep the command line to what needs it": a
  CLI command exists only when a program runs it, when it must work without
  the daemon or a browser, or when the web UI cannot do the job. Every command
  is listed with its reason, and the list is the test. Pruning the other kinds'
  commands to that rule is follow-up work.
- mcp-gateway: Coffer's built-in tools are `coffer__search_tools` alone.
- experimental-features, agent-registry, vault-storage, vault-sync, daemon:
  stop naming `coffer__write`, triggers, the two removed hook events and the
  `memory-triggers` directory.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `knowledge`: material arrives as inbox files; no tool, no CLI; no writer is exempt from the newer-or-better-evidenced rule.
- `memory`: notes are editable in the web UI and on disk; no triggers; two hook entries; no CLI beyond the hidden hook entry point.
- `resource-framework`: the parity rule becomes the minimal-CLI rule; `coffer path` loses its knowledge and memory targets.
- `mcp-gateway`: one built-in tool.
- `experimental-features`: the knowledge gate no longer closes a tool.
- `agent-registry` (and its `claude-code` and `codex` children): Coffer's memory hook is two entries.
- `vault-storage`, `vault-sync`: the vault no longer holds `memory-triggers/`.
- `daemon`: the hook entry point is internal.
- `web-ui`: the memory editor.

## Impact

- Removed: `coffer__write`; `coffer knowledge *`; `coffer memory *` except the
  hidden `coffer memory hook`; `coffer path knowledge|memory`;
  `POST /api/v1/knowledge/material`; `GET|POST /api/v1/memory/triggers`,
  `POST /api/v1/memory/triggers/{id}/arm|disarm`,
  `DELETE /api/v1/memory/triggers/{id}`; every other knowledge or memory route
  the web UI does not call; the `memory_trigger_*` audit events; the trigger
  domain, store and service and the hook's deny and error-context paths.
- Added: a route that saves one memory's body, and a `memory_note_edited`
  audit event.
- Upgrade: a one-time migration deletes `vault/memory-triggers/` (the deletion
  syncs like any other); the reconciler rewrites each installed memory hook
  from four entries to two on its first pass. The two remaining entries keep
  their command, so Codex's approvals for them still hold.
- Policy: `.agents/openspec.md` "End-to-End Deliverable Rule" states the
  minimal-CLI rule in place of REST/CLI parity.
- Docs: the knowledge and memory guides and architecture pages (en and zh), the
  CLI, REST and MCP tool references, the glossary, the filesystem reference,
  and the ADRs "Memory reaches a session at three moments", "Knowledge is plain
  files", "Knowledge curation", "Coffer ships its own skill" and "Agent hook
  installation".
- Canvas: the Memory page's partition boards gain the memory editor; the Agents
  canvas's Hooks tab shows two memory hook entries.
