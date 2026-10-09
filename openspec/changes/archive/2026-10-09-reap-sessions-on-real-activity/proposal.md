## Why

On 2026-10-07 the owner's Mac held 12 concurrent agent MCP sessions (6 Claude Code, 6 Codex App), four of the Codex ones alive for more than a day. Each session owns its own upstream set, and the idle reaper never dropped them: an open GET stream refreshed the session's idle timer every 15 s, and Codex App keeps its stream open.

## What Changes

- Only downstream requests and forwarded upstream notifications count as session activity. An open notification stream, and its 15 s keepalive wake-up, no longer do.
- The default idle window drops from 30 to 10 minutes (`COFFER_MCP_SESSION_IDLE_S` still overrides it).
- A reaped session ends its open stream cleanly; the client's next request gets `404` and the shim handshakes again.
- ADR `session-subprocess-model` keeps one upstream set per session and records why cross-session sharing was rejected again.
