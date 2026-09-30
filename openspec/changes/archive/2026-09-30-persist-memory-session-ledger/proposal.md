## Why

The per-session ledger — which notes each session was given, and which triggers already held one of its commands — lived only in the daemon's memory. After a daemon restart a running session could be given the same note again, or have a trigger hold a second command.

## What Changes

- The ledger is rebuilt after a restart from the audit log. Every delivery fire is already a `memory_delivery_fired` event naming its session, its notes and its trigger. Before the daemon answers its first prompt or command, it replays the fires of the last seven days into the ledger.
- No table is added: the audit log is the durable record.
- A rebuild that fails is logged and leaves the ledger empty.

## Capabilities

### New Capabilities

### Modified Capabilities
- `memory`: what a session was given survives a daemon restart.

## Impact

- Backend: `application/memory/{session_ledger,ledger_restore,retrieval,hook_service}.py`, `surfaces/http/memory_wiring.py`.
- Tests: `tests/unit/memory/test_ledger_restore.py`, `tests/integration/memory/test_session_ledger_restart.py`.
- Docs: the memory guide and architecture page.
