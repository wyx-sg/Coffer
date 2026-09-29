## Why

The CLI reshape (`reshape-cli-and-mcp-surface`) left six commands that repeat another command, guard nothing, or are never reached: two spellings of agent registration, a discard that only refuses, a connection report that `coffer agent show` already prints, a knowledge save whose fingerprint guard re-reads the file it is about to overwrite, a per-partition distil that `coffer memory sync` already runs, and a generic `add` no kind registers. Each one is a second way to say the same thing, or a command that protects nothing, and each is surface the docs, the parity table and the tests have to keep describing.

## What Changes

- **BREAKING** `coffer adopt agent <type>` is removed. A detected agent is registered with `coffer agent add <type>`, the one command that posts to `POST /api/v1/agents`; the `agent` row of `coffer scan` names that command. `coffer adopt` and `coffer discard` cover `skill` and `mcp`.
- **BREAKING** `coffer discard agent` is removed; it only printed a refusal.
- **BREAKING** `coffer agent connection <name>` is removed. `coffer agent show <name>` prints the same report as its `coffer_connection` field, part by part, from the same `GET /api/v1/agents/{uid}/coffer-connection`. `coffer agent connect` and `coffer agent disconnect` are unchanged.
- **BREAKING** `coffer knowledge save` is removed. A knowledge document is a plain file edited on disk under `coffer path knowledge <collection>`; `PUT /api/v1/knowledge/file` stays for the web UI's editor, and the parity table lists it as a file-backed route answered by `coffer path`.
- **BREAKING** `coffer memory distil <partition>` and `POST /api/v1/memory/partitions/{uid}/distil` are removed. `coffer memory sync` / `POST /api/v1/memory/sync` aggregates and then distils every partition that gained entries; a partition whose pass is already running is reported as skipped. The distil pass, its worker and its timer are unchanged.
- The generic `add <name> --config JSON` of the CLI's lifecycle-verb factory is removed. Every group that offers `add` registers its own; no group's commands change.
- Docs: README's Agents and Knowledge bullets, the agents guide's description, the `coffer-guide` skill's `coffer log` options and the resource-framework architecture page's description of each group's verbs are corrected to the code.

## Capabilities

### New Capabilities

### Modified Capabilities
- `agent-registry`: discovery candidates are registered with `coffer agent add <type>`; the Coffer connection is read on the command line through `coffer agent show`; the surface roster and the discovery surface follow.
- `resource-framework`: the lifecycle verbs no longer include a generated `add`; `adopt`/`discard` cover only the kinds that offer them, with no refusing command for the rest; the parity table lists `PUT /knowledge/file` among the file-backed routes and no longer lists `adopt agent`, `discard agent`, `agent connection`, `knowledge save` or `memory distil`.
- `knowledge`: the CLI group no longer offers `save`.
- `memory`: the REST family no longer runs a distil pass over one partition, and the CLI group no longer offers `distil`; a busy partition is skipped by Update memory rather than refused by a per-partition trigger.

## Impact

- Backend: `surfaces/cli/scan_cmd.py`, `agent_cmd.py`, `agent_connection_cmd.py`, `knowledge_cmd.py`, `memory_cmd.py`, `_kind_verbs.py`; `surfaces/http/memory/partition_routes.py`, `memory/schemas.py` (`DistilResultOut`), `memory/distil_state.py`, `memory_wiring.py`, `upkeep_routes.py`; the `coffer-guide` skill asset.
- Contracts: memory (`/memory/partitions/{uid}/distil` and `DistilResultOut` removed), resource-framework (upkeep-runs description); frontend codegen.
- Tests: CLI parity table, scan, agent, knowledge, memory and kind-verb CLI tests; memory HTTP and integration tests move from the per-partition route to `POST /memory/sync`.
- Docs: guides (agents, connect-a-client, knowledge, memory), start (quickstart), architecture (knowledge, memory, resource-framework), README, generated CLI and REST references; `scripts/check_removed_commands.py` lists the removed phrases.
