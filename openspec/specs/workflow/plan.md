# Implementation Plan — Workflow

Authority is [`spec.md`](./spec.md); the wire contract is
[`contracts/api.openapi.yaml`](./contracts/api.openapi.yaml); the state is
[`data-model.md`](./data-model.md).

## What this composes rather than builds

The layer is deliberately thin because four things it needs already exist and
are not rebuilt here:

| Need | Already in the vault |
|---|---|
| Run an agent, stream it, interrupt it | the turn platform (`application/chat/`) — a node's work is one conversation |
| Reach an external system | the MCP gateway and its registered servers |
| Say how a job is done | `skill` resources, bound by a node |
| Deliver an approval to the developer | `channel` resources |
| Keep bulk content | files on disk, the way knowledge does |

What is genuinely new: a state machine, four tables, a background advancer, a
context composer, and one gate inside the gateway.

## Module layout

```text
backend/coffer/domain/workflow/
  template.py        # template value objects + the validation rules (pure)
  run.py             # Run, NodeAttempt, Approval; the status enums
  transitions.py     # legal transitions, allowed actions, next-node selection
  events.py          # the closed event vocabulary + the projection fold
  errors.py          # WorkflowVersionConflict, IllegalTransition, NotThisMachine…

backend/coffer/application/workflow/
  ports.py           # TurnPlatformPort, ArtifactStorePort, RunRepoPort, ChannelNotifyPort
  kind.py            # the `workflow` resource kind: schema + validation entry
  run_service.py     # create / list / get / delete / signals, version checks
  node_service.py    # node actions, attempts, ad-hoc tasks
  node_driver.py     # node -> conversation, subscribe the turn, collect the result
  context_composer.py# the shared context every node opens with
  catalogue.py       # CATALOG.md from the artifact directory
  approval_service.py# create, decide idempotently, expire
  gate.py            # the write-class decision, independent of the gateway
  advance_worker.py  # the background advancer

backend/coffer/infrastructure/workflow/
  models.py          # ORM for the four tables
  repository.py      # the repos behind the ports
  paths.py           # the only place a run path is constructed; segment guard
  artifacts.py       # read/write/collect artifacts

backend/coffer/surfaces/http/workflow/
  schemas.py         # hand-written Pydantic matching the yaml
  routes_runs.py  routes_nodes.py  routes_approvals.py  routes_artifacts.py
  wiring.py          # composition-root wiring

backend/coffer/surfaces/cli/workflow_cmd.py    # registered in cli/main.py, like every other kind

frontend/src/pages/WorkflowsPage.tsx        # the run list
frontend/src/pages/WorkflowRunPage.tsx      # stages, nodes, main thread, approvals
frontend/src/components/workflow/*.tsx
frontend/src/hooks/useWorkflowRuns.ts  useWorkflowRun.ts
```

Every Python file stays ≤ 400 lines, every page ≤ 200 and component ≤ 250 —
which is why `run_service` and `node_service` are separate, and why the driver,
the composer and the catalogue are three modules rather than one.

## The changes outside this layer

Three, each small and each named here so review can find them:

1. **The shim reports a run identity.** `surfaces/shim/bootstrap.py` adds one
   `_meta` key, read from the environment. Absent for every ordinary shim
   launch.
2. **A node's turn sets that environment variable.** `claude_sdk_provider`
   passes `env` through to the adapter (the seam is already there and unused);
   `codex_provider` already passes `env` and gains the key.
3. **The gateway consults the gate.** `MCPGatewaySession._handle_tools_call`
   asks `application/workflow/gate.py` before dispatching an upstream tool when
   the session carries a run identity. A session without one is untouched — no
   behaviour changes for any conversation that is not a workflow node.

A fourth change is data, not code: `mcp_server` config gains
`tool_write_class`.

## Order of work

**Foundations** — nothing depends on anything else here, so these go together.

- The domain: template validation, transitions, the event fold. Pure, table-driven tests.
- The infrastructure: ORM, one Alembic migration, paths with the segment guard, the artifact store.
- The attribution plumbing: shim `_meta` key, provider `env`, and the gateway reading it. No gate yet — just the identity arriving, proven by a test.

**The engine** — depends on the foundations.

- `run_service` and `node_service`: the command surface, version checks, event append, projection.
- `node_driver` + `context_composer` + `catalogue`: a node becomes a conversation, opens with the shared context, and leaves artifacts behind. Driven in tests by a fake agent adapter, as the chat platform's own tests already do.
- `approval_service` + `gate` + the gateway call site: the held call, the decision, the expiry.
- `advance_worker`: the run moves without being asked.

**The surfaces** — depend on the engine.

- HTTP routes and schemas, registered in the contract-coverage table.
- CLI handlers.
- The two web pages and their hooks, after `npm run codegen`.

**Closing** — the acceptance markers for every scenario in `spec.md`, the
roadmap entry, the architecture table's eighth kind, and `make verify`.

## Testing approach

- **Domain** is pure and table-driven: every legal transition, every illegal one, the projection fold against a handwritten event list.
- **Application** runs whole runs against a fake agent adapter — no real agent, no tokens, no network. This is the tier that proves a run advances, redirects, retries, loops and stops at its ceiling.
- **The gate** is tested from both sides: the decision function alone, and the gateway call site holding, releasing, expiring and refusing.
- **Restart** is a real test, not a claim: build a run, drop the projection, rebuild from events, compare.
- **E2E** drives one three-stage template through the web UI against a daemon on an isolated `HOME`.

Every test that touches the run root sets `$COFFER_WORKFLOW_ROOT`. Unset, it
resolves to the developer's real vault, and this layer's tests create, move and
delete directories.

## What is deliberately left for later

Parallel nodes, multi-repository runs as a first-class field, scheduled starts,
and any MCP tool that lets an agent drive the engine. Each is in
[`spec.md`](./spec.md)'s Out of Scope with the reason.
