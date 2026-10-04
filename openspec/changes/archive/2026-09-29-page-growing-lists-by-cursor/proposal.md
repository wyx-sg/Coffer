## Why

The lists that grow while someone reads them — the audit log, the MCP
invocation log, an agent's transcript sessions and the chat conversations —
page by `limit` with `since` or `offset`, so a row written between two page
reads shifts every later page: rows repeat or are skipped. The ADR
[The Wire Contract Is Generated From the Pydantic Models](../../../docs/decisions/wire-contract-generated-from-the-pydantic-models.md)
fixes the convention: growing lists page by an opaque cursor.

## What Changes

- One paging convention for growing lists: `limit` plus an opaque `cursor`
  on the request, `next_cursor` on the answer (`null` on the last page), a
  stable order with a unique tie-break, and a page after a cursor that holds
  exactly the rows that followed the cursor's row. A cursor that is malformed
  or was issued for another list or other filters is `400 CURSOR_INVALID`.
- The audit log (`GET /api/v1/audit`, `coffer log audit`), both invocation-log
  reads (`coffer log mcp`), the transcript session listing and the active and
  archived conversation listings follow it. The transcript listing's `offset`
  is replaced; `since` stays as a filter where a list had it.
- The single-session transcript read keeps `limit`/`offset`: it windows one
  append-only file, whose earlier turns never move.

## Impact

- resource-framework: the convention and the audit read.
- mcp-gateway, agent-registry, chat: their list reads.
- CLI: `--cursor` on `coffer log audit` and `coffer log mcp`, and the JSON
  output carries `next_cursor`.
