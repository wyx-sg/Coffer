# Tasks

## 1. Hooks

- [x] 1.1 Four entries per agent, one `coffer memory hook` command, JSON for both agents
- [x] 1.2 Reconciler judges the set of events and every entry's command; Codex trust over every entry
- [x] 1.3 Agent hooks listing reports Coffer's hook as its four entries

## 2. Retrieval, guard, triggers

- [x] 2.1 BM25 ranker, floor, trivial-prompt skip, 1.5 KB ceiling, per-session dedupe
- [x] 2.2 Trigger files in `vault/memory-triggers/`, segment matching, deny once, error context
- [x] 2.3 REST `/memory/triggers` and `coffer memory trigger list|add|arm|disarm|delete`
- [x] 2.4 Distil proposes triggers unarmed
- [x] 2.5 Fail open in the CLI
- [x] 2.6 Vault sync mirrors and applies `memory-triggers/`

## 3. Delivery views

- [x] 3.1 `GET /memory/deliveries` and `GET /memory/partitions/{uid}/delivered`, `coffer memory delivered`
- [x] 3.2 Notes read from tool-call paths, `unavailable` when transcripts are missing

## 4. Tests (acceptance markers on every new scenario)

- [x] 4.1 Unit: ranking, floor, dedupe, trigger matching, once per session, trigger store
- [x] 4.2 Integration on a fake home: both agents' hook JSON, fail open, trigger lifecycle, counts, Delivered view
- [x] 4.3 Update the existing hook, reconcile and parity tests

## 5. Docs and contracts

- [x] 5.1 `make contracts`; audit event and error labels in both interface languages
- [x] 5.2 docs-site memory architecture and guide, including the per-turn-rule limit
- [x] 5.3 `make verify`, then archive this change
