## 1. Backend

- [x] 1.1 Pure capture module: redact injected values, credential headers, secret-named fields; cut each part at 16 KB
- [x] 1.2 `mcp_invocations.content_json` column and migration; lists defer it, one call reads it
- [x] 1.3 Capture arguments, result and error in the gateway, the built-in tools and the custom HTTP tool client (request and response)
- [x] 1.4 Scrub every recorded string with the plaintext-secret rules in the invocation writer
- [x] 1.5 `record_call_content` setting in daemon-config.json, its routes and audit event
- [x] 1.6 `GET /api/v1/mcp/invocations/{id}`; `coffer log call`; `coffer settings call-content`; ids in `coffer log mcp`
- [x] 1.7 Audit details say what changed; text edits carry a capped diff
- [x] 1.8 Mirror each audited event's details into its daemon.log line, capped at 2 KB

## 2. Frontend

- [x] 2.1 Call drawer: Arguments, Result / Error, Request, Response, cut note, not-recorded state
- [x] 2.2 Settings › Data › History: Record tool call content switch
- [x] 2.3 en + zh copy

## 3. Docs and design

- [x] 3.1 ADR: record tool call content, redacted and bounded (Audit and Retention rewritten to point at it)
- [x] 3.2 Activity guide, observability, MCP gateway architecture, CLI reference (en + zh)
- [x] 3.3 Canvases: System (Activity call drawer), Shell (Settings › Data)
