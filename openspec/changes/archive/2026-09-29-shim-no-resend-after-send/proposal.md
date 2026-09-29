## Why

When a POST from `coffer-mcp-shim` to the daemon fails and a restarted daemon is found, the shim resends the same envelope once. A read timeout, a connection reset mid-response or a protocol error can happen after the old daemon has received the request and run it. Resending such a `tools/call` runs the upstream tool a second time, which duplicates writes for tools that are not idempotent.

## What Changes

- The shim resends a request to a restarted daemon only when the request cannot have run: the failure happened before the request was sent (`httpx.ConnectError`, `httpx.ConnectTimeout`), the method is not `tools/call`, or the old daemon rejected it with 401.
- A `tools/call` whose send may have landed still rebinds the shim to the new daemon, so later calls work. Its own reply is a JSON-RPC `-32603` error saying the daemon restarted during the call and the call may or may not have run.
- Docs: the shim's restart-recovery step in the MCP gateway architecture page states the rule.

## Capabilities

### New Capabilities

### Modified Capabilities
- `mcp-gateway`: "Present Coffer as one MCP server" states when a shim session resends a request after a daemon restart and adds a scenario for a `tools/call` interrupted mid-call.

## Impact

- Backend: `surfaces/shim/main.py` (`_Bridge._handle_envelope`).
- Tests: `backend/tests/integration/surfaces/shim/test_shim_resend.py`.
- Docs: `docs-site/architecture/mcp-gateway.md`.
