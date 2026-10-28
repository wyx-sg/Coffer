## Why

A SeaTalk direct message asking why signup QPS spiked got a reply that was a
fragment of English notes about client ids and `logcli --hours`, ending in a
stray code fence. The Codex app-server Coffer spawned for the turn had also
started Codex's background memory consolidation agent (its "phase 2"), on a
thread of its own. Coffer's notification pump mapped every notification it
saw, whatever thread it named: the memory agent's streamed text became the
reply, and its `turn/completed` ended the turn. Coffer then closed the
app-server, which interrupted the real turn before it had answered. The same
would happen with any sub-agent the turn spawns.

## What Changes

- The Codex adapter learns the turn's thread id from the `thread/start` or
  `thread/resume` result and maps only notifications of that thread (and those
  naming none). Another thread's text, completion and errors are dropped.

## Impact

- `backend/coffer/infrastructure/chat/codex_mapping.py` (`is_own_notification`,
  `CodexParseState.thread_id`), `codex_agent.py` (pump filter).
- Tests: unit `test_codex_mapping.py`, integration
  `test_codex_app_server_agent.py`; the provider tests' fake app-server now
  answers with the thread id its frames name.
- Spec `chat`, edited directly (`skip_specs: true`).
- docs-site architecture `chat.md` (en, zh). No UI change, no canvas change.
