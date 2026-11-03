## Why

Memory and knowledge were split by origin: what agents learned versus what
someone wrote down. On the maintainer's Mac about 30 of 74 global memories were
notes on outside systems and processes, which need a source and a recheck date,
and none of 180 Claude Code sessions opened a `coffer_*.md` copy: only text a
session loads is used. The options are argued in ADRs
`memory-is-about-the-person-knowledge-is-about-the-world` and
`claude-code-reads-other-agents-memories-as-text`.

## What Changes

- Memory holds the person, how to work with them and a project's state;
  knowledge holds outside systems, teams and processes; skills hold procedures.
- Coffer flags task material from where its agent filed it (a Codex task-group
  memory, a Claude Code `reference` memory). Task material stays with its own
  agent until it is sorted back into memory.
- The Memory page counts what waits to be sorted and offers **Sort into
  knowledge**, a hand-off to Claude Code in the terminal; the attention list
  carries one item once ten wait. `coffer memory sorted` records each sorting
  under `vault/memory/sorted/`.
- Claude Code gets no `coffer_*.md` copies and no `-coffer-global` project: a
  project's memories go as text into its `MEMORY.md` block (4 KB), global ones
  as text into the rules file (8 KB).
- CLI: `coffer memory to-sort`, `sort`, `sorted`; `entries --project global`.

## Impact

- Backend memory layer (writer, sync plan, view, routes, attention, CLI),
  frontend Memory page and Overview, docs-site, `coffer-guide`.
- Spec `memory` (requirements and data model), edited directly
  (`skip_specs: true`): two Claude Code writer requirements replaced by one,
  three requirements added.
- ADRs `global-memories-in-claude-code-live-in-a-global-project` and
  `the-claude-code-rules-file-lists-only-standing-memories` are replaced and
  deleted.
