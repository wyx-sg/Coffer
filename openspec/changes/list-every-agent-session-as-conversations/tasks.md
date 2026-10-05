## 1. Backend — cross-agent listing

- [ ] 1.1 Application service `AgentSessionsListing` over `NativeSessionService`: ask the selected agents concurrently, merge by `(last_activity_at desc, agent key, session_id)`, the per-agent `{c, skip, done}` cursor bound to `q`/`source`/`agent`, `unavailable` for an agent whose listing raises
- [ ] 1.2 `source`: channel uids only → page the conversation index (move `Narrowing` and the index paging there); `local` / mixed → post-filter the merge on the conversation binding, reading up to five agent pages per agent per request
- [ ] 1.3 Route `GET /api/v1/agent-sessions` (`limit`, `cursor`, `q`, `source`, `agent`) with `AgentSessionOut` + `agent_key`, no `total`, `unavailable`
- [ ] 1.4 Delete `GET /api/v1/chat/conversations` (the list) and `count_conversations`; keep `/chat/conversations/{id}` read, rename, delete and interrupt
- [ ] 1.5 Tests with `acceptance("agent-registry", …)`: "sessions from two agents are listed in one order", "the listing narrows by source and agent", "a channel conversation with no session yet is listed under its channel", "one agent failing leaves the others listed"; move the removed requirement's markers ("the conversation list is ordered by activity, not by creation", "the conversation list pages by cursor", "the conversation list narrows by source and agent on the server", "search matches titles and working directories") off or onto the new scenarios

## 2. Backend — blank session in a terminal

- [ ] 2.1 `terminal_command.blank_command(agent, cwd)`; `FsTerminalRequest` takes at most one of `resume` / `prompt`; both is `FS_TERMINAL_INVALID`
- [ ] 2.2 Test `acceptance("daemon", "a body with neither resume nor prompt starts a blank session")`; update "an unsafe session id is refused before anything starts"

## 3. Contracts

- [ ] 3.1 `make contracts` — `agent-registry`, `chat` and `daemon` OpenAPI regenerated, frontend types regenerated; review the diff
- [ ] 3.2 `openspec/specs/chat/data-model.md`: the index is no longer listed on its own; note the merged listing

## 4. Frontend — Conversations page

- [ ] 4.1 `lib/api/agentSessions`: `listAll`; `useAgentSessionsList` infinite query over it; `conversationRow` / `sessionRow` collapse to one mapping with `agentKey`
- [ ] 4.2 `ConversationsIndex` over the new listing: Source pill (This Mac + channels), Agent pill, search, `?source=local|<uid>`; the unavailable line with Retry; header subtitle reworded
- [ ] 4.3 Row actions route by row: a row with a session renames / deletes through `/agents/{uid}/sessions/{id}`, a channel row with none through `/chat/conversations/{id}`
- [ ] 4.3a `SessionList` gains a header row naming its visible columns (Title, Source, Agent, Directory, Last active), above the day groups
- [ ] 4.4 `AgentSessionsTab` becomes the same list narrowed to its agent (no agent column)
- [ ] 4.5 Tests with `acceptance("chat", …)`: every MODIFIED scenario of "Show every agent's sessions on the Conversations page", plus "one agent's sessions that cannot be read are named above the list"

## 5. Frontend — New conversation

- [ ] 5.1 `NewConversationDialog`: agent (last chosen, `localStorage`), working directory (workspace default, folder picker), confirm split button Open in <terminal> ▾ other terminals; refusal shown in the dialog
- [ ] 5.2 Header button on Conversations; beside the search on the Sessions tab with the agent preset; disabled with a reason when no agent is managed
- [ ] 5.3 Tests: `acceptance("chat", "New conversation starts the chosen agent in the chosen directory")`, `acceptance("chat", "a refused start keeps the dialog open")`, `acceptance("agent-registry", "New conversation on the Sessions tab starts this agent")`

## 6. Frontend — channel Overview

- [ ] 6.1 Replace `ChannelRecentConversations` with the Conversations from this channel link
- [ ] 6.2 Test `acceptance("channels", "a channel's Overview links to its conversations instead of listing them")`

## 7. Docs and canvases

- [ ] 7.1 Citations of "Show channel conversations on the Conversations page" → the new title (backend, frontend, `channels` spec "List every Coffer-hosted channel on one management surface", ADR `sidebar-grouped-by-what-the-person-comes-to-do`)
- [ ] 7.2 `docs-site/guides/chat.md`, `guides/channels.md`, `guides/web-ui.md`, `architecture/chat.md` — en and zh
- [ ] 7.3 e2e `shell_conversations.spec.ts` over the new listing and New conversation
- [ ] 7.4 Design canvases: Conversations page, New conversation dialog, agent Sessions tab, channel Overview

## 8. Close

- [ ] 8.1 `make verify`
- [ ] 8.2 `npx openspec archive list-every-agent-session-as-conversations --yes` in the same PR
