## 1. Ledger across restarts

- [x] 1.1 `restore_from_audit` replays the last seven days of delivery fires into the ledger
- [x] 1.2 `SessionLedger.ready` restores once before the first answer; a failure is logged and leaves it empty
- [x] 1.3 Retrieval and the trigger guard wait for the restore

## 2. Tests and docs

- [x] 2.1 Unit tests for the replay and the once-only restore
- [x] 2.2 Integration test across two daemon lifetimes on one database
- [x] 2.3 Memory guide and architecture page
