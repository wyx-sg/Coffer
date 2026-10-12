## 1. Backend

- [x] 1.1 `MemorySyncView.entry`: one memory's text (paths expanded here) and per local agent its copy's state and file
- [x] 1.2 `GET /api/v1/memory/sync/entries/{entry_id}` and `coffer memory show`; contract and frontend types regenerated
- [x] 1.3 The preview's rows carry each memory and action (`items`)
- [x] 1.4 Integration test: a memory opens with its text and where each agent holds it; preview items

## 2. Frontend

- [x] 2.1 Memory page: scopes beside the scope's memories, notable copy states only, `?scope=` / `?source=` / `&memory=`
- [x] 2.2 Memory drawer: locations first, then the text; folds past four agents
- [x] 2.3 One "needs you" banner and drawer; preview folded by agent and project
- [x] 2.4 Agent Memory tab: Memory sync section; Codex import switch moved there
- [x] 2.5 Old project addresses redirect; project page removed
- [x] 2.6 Shared drawer: Maximize / Restore
- [x] 2.7 Component tests and the e2e walk updated

## 3. Docs and design

- [x] 3.1 ADR and research note
- [x] 3.2 docs-site guides en + zh, CLI reference
- [x] 3.3 Canvases: Context (Memory), Agents (Memory tab), Foundations (drawer)
