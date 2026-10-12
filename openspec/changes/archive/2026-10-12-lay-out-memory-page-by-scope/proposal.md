## Why

The Memory page laid out the sync's machinery — warning panels, a preview table of counts, a projects table, an agents table — and showed no memory: a memory took two clicks and its text was nowhere in the product. Agent settings on the page grew with every agent. The maintainer found it confusing; the decision and the options are in ADR [The Memory Page Lists the Memories by Scope](../../../docs/decisions/memory-page-lists-memories-by-scope.md).

## What Changes

- The Memory page becomes a split view: scopes (global, projects here, projects not checked out) beside the open scope's memories, with search and type / origin filters (`/memory?scope=`, `?source=`).
- A memory's copy state shows on its row only when it waits, or the agent edited or removed it.
- A memory opens in the shared drawer: one line per local agent (state, file, Open / Reveal), then its text, read only. New route `GET /api/v1/memory/sync/entries/{entry_id}` and command `coffer memory show`.
- Everything that needs the person (preview, unreadable sources, withheld memories, agents Coffer cannot write into) is one banner and one drawer; the preview is folded to per-agent-and-project counts and opens down to each memory (the preview carries `items`).
- Agent switches, copies, **Curate now** and Codex's import switch move to each agent's Memory tab ("Memory sync" section) with **Open Memory ›**.
- `/memory/projects/<folder>` and `/memory/global` redirect to the scope; the project page is removed.
- The shared drawer gains **Maximize** / **Restore**.

## Impact

- Specs: memory (four requirements), agent-registry ("Show what Coffer manages for an agent in one row"), web-ui ("Use one shared table for every list surface").
- Code: `sync_view.py`, `sync_report.py`, `sync_routes.py`, `cli/commands/memory.py`; frontend Memory page and components, agent Memory tab, `Drawer`.
- Docs: guides (memory, web UI), CLI reference; canvases Context, Agents, Foundations.
