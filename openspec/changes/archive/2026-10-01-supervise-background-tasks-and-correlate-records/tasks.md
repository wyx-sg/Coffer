## 1. Supervision

- [x] 1.1 Add `application/runtime/supervisor.py`: `spawn`, `spawn_restarting`, crash lines and counts, the shutdown sweep
- [x] 1.2 Move the channel runtime, each Telegram poll loop and each SeaTalk websocket supervisor onto `spawn_restarting`, and channel ingest, render and turn tasks onto `spawn`
- [x] 1.3 Move the periodic workers (reconciler, retention, curation, memory, sync, price refresh, attention watch) onto `spawn_restarting`, and the other fire-and-forget tasks onto `spawn`
- [x] 1.4 Sweep the supervisor last in the shutdown sequence
- [x] 1.5 Add `scripts/check_bare_tasks.py` to `make lint`, with its allow-list and tests

## 2. Loop lag and status

- [x] 2.1 Add `application/runtime/loop_lag.py` and start the probe in the lifespan
- [x] 2.2 Add the `runtime` block to `GET /api/v1/daemon/status` and print it in `coffer daemon status`

## 3. Correlation ids

- [x] 3.1 Add `application/runtime/correlation.py` and stamp its ids on every log line
- [x] 3.2 Bind the MCP session id in `POST /mcp`, and a turn's conversation and turn ids around the turn's spawn
- [x] 3.3 Migration 0137: `trace_id`, `conversation_id`, `turn_id` on `audit_log`, `trace_id` on `mcp_invocations`
- [x] 3.4 Record the ids on audit rows and invocations; filter by `trace_id` on the three routes and `--trace` on `coffer log audit|mcp|daemon`
- [x] 3.5 Show the trace id in the Activity drawer

## 4. Docs

- [x] 4.1 ADR `background-work-runs-supervised-and-correlated` (Proposed) and its index entry
- [x] 4.2 docs-site `architecture/observability.md` (en and zh) and the regenerated CLI reference
- [x] 4.3 Data models of resource-framework and mcp-gateway
