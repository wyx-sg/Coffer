## 1. Slimming

- [x] 1.1 Remove OpenAPI import, re-import and diff (backend, CLI, UI, docs, specs)
- [x] 1.2 jsonschema library for argument checks, with ADR
- [x] 1.3 Remove the per-environment timeout and reach `projects`
- [x] 1.4 Purpose wording; skill line on pinning versions

## 2. Small changes

- [x] 2.1 Every response header in a test, masked; drop `diagnostic_headers`
- [x] 2.2 Exact tool name first in search, with ADR
- [x] 2.3 Skip SSE entries at import and adopt, with ADR
- [x] 2.4 Elicitation relay

## 3. Gateway

- [x] 3.1 Real failure reason (HTTP kind or status, stdio exit with last stderr line)
- [x] 3.2 One hand-off per server and group; drop per-call hand-off and derived status fields, with ADR
- [x] 3.3 Lists from the saved catalogue; start a server only for a call (ADR revision)
- [x] 3.4 Log fixes: own-line Coffer lines, prune deleted servers' logs, SDK 404 noise, empty header values
