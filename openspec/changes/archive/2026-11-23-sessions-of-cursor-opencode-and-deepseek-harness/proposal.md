## Why

The owner asked for Cursor, OpenCode and DeepSeek Harness to get every feature each can take, and chose (2026-11-23) that their Sessions tab list the agents' own sessions, not only the ones Coffer ran. None of the three lists every folder's sessions on its command line.

## What Changes

- Coffer reads, read-only, the store each agent keeps: OpenCode's `opencode.db` (`session` in 1.x, `session_v2` in 2.x), DeepSeek Harness's session folders with their cached projection, Cursor's per-chat `store.db`.
- A store that cannot be read lists the conversations Coffer ran on the agent instead of failing; the reason is logged.
- OpenCode deletes through `opencode session delete` (`--standalone` on 2.x). The three have no command to rename, and DeepSeek Harness and Cursor none to delete, so a row's menu leaves out what its agent cannot do.
- Cursor and OpenCode sessions open in the terminal (`cursor-agent --resume`, `opencode --session`); DeepSeek Harness has no terminal interface.
- The three types get the `sessions` feature; the support table marks it ✓.
- Chat fix found on the way: OpenCode takes its project folder from `PWD`, so every one-shot turn sets it (shipped with the drivers' PR).
- `docs/TODO.md` records the deferred DeepSeek Harness model connection.

## Capabilities

### Modified Capabilities

- `agent-registry`: new requirement "List the sessions an agent keeps in its own store"; "List an agent's native sessions through the agent", "Rename and delete a native session through the agent" and "Open an agent's sessions from its Sessions tab" point at it. The main spec is edited directly, so this change carries no delta.

## Impact

Backend agent infrastructure (`cli_native_sessions`, `native_session_sources`), the application's `FallbackSessionSource`, the HTTP wiring and `IndexedSessionSource`, terminal commands, the web UI's session rows and Sessions tab, tests (integration with built stores, agent-cli listing after a real turn), the ADR `sessions-of-cursor-opencode-and-deepseek-harness-are-read-from-their-stores`, and the docs-site agents and chat guides (en and zh).
