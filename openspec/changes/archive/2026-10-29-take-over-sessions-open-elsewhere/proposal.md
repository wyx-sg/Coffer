## Why

A SeaTalk conversation on a Codex session kept answering "This session is open
in a terminal" long after the person had closed the terminal. Recent Codex CLIs
attach to a shared background app-server (`codex app-server --managed-daemon`)
that holds the thread's writer lock; with a turn left waiting on an approval it
never unloads the thread. The reply blamed a terminal that was gone, and a
channel used from a phone cannot "continue there". The person asked for the
channel to take the session over instead. The options are argued in ADR
`a-coffer-turn-takes-over-a-session-open-elsewhere`.

## What Changes

- Before a turn resumes a session, terminal processes naming it (outside the
  daemon's tree) are ended instead of refusing the turn.
- When Codex answers "already has an active writer", the Codex adapter frees
  the thread once and resumes it again: through the background app-server's
  control socket (join, interrupt a running turn, unsubscribe, wait for the
  unload), or by ending a terminal `codex` that holds the lock.
- A session held by anything else (the Codex app, an editor) is refused with a
  new reply naming that case.

## Impact

- `infrastructure/chat/session_takeover.py` (was `session_in_use.py`), new
  `codex_thread_release.py`; `codex_agent.py`, `codex_provider.py`,
  `turn_orchestrator.py`, `ports.py`; `SESSION_IN_USE_MESSAGE` and the web
  error text. `websockets` becomes a direct dependency.
- Spec `chat` requirement renamed to "Take over a session open elsewhere" with
  new scenarios, edited directly (`skip_specs: true`); spec `channels` citation.
