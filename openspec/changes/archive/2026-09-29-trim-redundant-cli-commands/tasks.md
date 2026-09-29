No `design.md`: each removal points at the command or route that already does the same thing, so there is no choice to explain.

## 1. CLI

- [x] 1.1 Remove `coffer adopt agent` and `coffer discard agent` (`surfaces/cli/scan_cmd.py`); the scan's `agent` row names `coffer agent add <type>`
- [x] 1.2 Remove `coffer agent connection` (`surfaces/cli/agent_connection_cmd.py`); `coffer agent show` keeps printing the connection part by part
- [x] 1.3 Remove `coffer knowledge save` (`surfaces/cli/knowledge_cmd.py`)
- [x] 1.4 Remove `coffer memory distil` (`surfaces/cli/memory_cmd.py`)
- [x] 1.5 Remove the generic `add` from the lifecycle-verb factory (`surfaces/cli/_kind_verbs.py`) and from `ALL_VERBS`
- [x] 1.6 Add each removed phrase, with its replacement, to `scripts/check_removed_commands.py`

## 2. REST

- [x] 2.1 Remove `POST /api/v1/memory/partitions/{uid}/distil`, `DistilResultOut` and the route's runner getter/setter; docstrings of `upkeep_routes.py`, `application/memory/update.py` and the memory wiring follow
- [x] 2.2 Contracts: memory (path and `DistilResultOut` removed, error list), resource-framework (upkeep-runs description); `memory/data-model.md`; frontend codegen

## 3. Tests

- [x] 3.1 CLI parity table: `adopt`/`discard` without `agent`, `agent` without `connection`, `knowledge` without `save`, `memory` without `distil`; `PUT /knowledge/file` moves to the file-backed routes as `path knowledge <collection>`
- [x] 3.2 `acceptance(agent-registry, "adopt a discovered agent from the command line")` on a test that registers the scanned agent with `coffer agent add`
- [x] 3.3 `acceptance(resource-framework, "an unknown or undiscardable row is refused")` on a test that finds no `discard agent` command
- [x] 3.4 `acceptance(memory, "a second distil pass over the same partition is refused while the first is running")` on the Update memory skip test and the worker tests; memory HTTP and CLI tests reach the pass through `POST /memory/sync`
- [x] 3.5 `acceptance(memory, "audit a requested aggregation and distil with their actor")` on a test that runs one Update memory
- [x] 3.6 Knowledge, memory and path CLI tests assert the removed commands are absent; kind-verb tests drop the generic `add`

## 4. Docs

- [x] 4.1 Guides (agents, connect-a-client, knowledge, memory), start (quickstart), architecture (knowledge, memory, resource-framework), README; `make docs-reference`
- [x] 4.2 README's Agents and Knowledge bullets, the agents guide's description, the `coffer-guide` skill's `coffer log` options, and resource-framework.md's description of each group's verbs corrected to the code

## 5. Verify and archive

- [x] 5.1 `make verify`-equivalent gates: ruff, mypy, lint-imports, pytest, frontend typecheck/lint/vitest/codegen check, docs reference, removed commands, file sizes, spec citations, acceptance audit, OpenSpec strict validation, doc numbering, contract
- [x] 5.2 Archive the change in the same PR (`npx openspec archive trim-redundant-cli-commands --yes`)
