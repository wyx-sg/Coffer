## 1. Metering and storage

- [x] 1.1 Per-wire usage readers and the spool (with the proxy)
- [x] 1.2 Ingest with de-duplication and daily rollups; migration 0111
- [x] 1.3 Retention: detail follows the MCP invocation window, rollups a year

## 2. Cost and reports

- [x] 2.1 Bundled price snapshot, per-connection prices, unpriced marking
- [x] 2.2 Summary by model / agent / day over ranges, request detail, CSV — REST and CLI

## 3. Quota

- [x] 3.1 Codex `account/rateLimits/read` + `updated` notifications
- [x] 3.2 Claude Code `rate_limit_event` from driven sessions
- [x] 3.3 Quota REST and CLI "as of"; the opt-in statusline wrapper

## 4. Tests and docs

- [x] 4.1 Parser golden tests, ingest replay, retention, routes, CLI, observers
- [x] 4.2 Usage and quota guide
