## 1. Workers

- [x] 1.1 Channel runtime on the wakeable loop, poked by resource hints and secret approvals, retry by timer
- [x] 1.2 Model proxy watchdog parks while idle; a state push wakes it
- [x] 1.3 Usage ingest follows the proxy: drains once when it stops, then parks
- [x] 1.4 MCP session reaper parks with no session

## 2. Tests and docs

- [x] 2.1 Tests for each worker's waking and parking
- [x] 2.2 Daemon architecture page (en, zh) and the ADR
