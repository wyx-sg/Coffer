## 1. Principles

- [x] 1.1 Amend principle IV (hand-off starts the default agent in the preferred terminal), en + zh

## 2. Backend — the message store goes (D)

- [ ] 2.1 Migration 0149: drop `chat_reply_files`, `chat_messages`, `chat_conversations.archived_at`; delete non-channel conversation rows and the conversation retention policy rows
- [ ] 2.2 Remove `MessageRepo`, reply-file recording and diffs, turn persistence, the streaming sweep, history passed to adapters, previews; keep title-from-first-message
- [ ] 2.3 Remove conversation archive/unarchive/batch, archived listing, conversation retention entries, chat-media uploads and their routes; keep transcription and document extraction (channel attachments use them)
- [ ] 2.4 Remove web-only routes: messages list, send, resend, pending, per-conversation SSE, attachment bytes, reply files, question answer, agent-config, web-reply mirror
- [ ] 2.5 Conversation listing: channel conversations only, search over title and directory, row carries cwd, session id, running, needs_you
- [ ] 2.6 Native session listing through the agents (Claude SDK `list_sessions`, Codex `thread/list`); remove the transcript parser, sidecar, warm worker and windowed read; `GET /api/v1/agents/{uid}/sessions`
- [ ] 2.7 Spec sync for D (chat, channels, agent-registry, resource-framework); contracts regenerated

## 3. Backend — rename and delete (C)

- [ ] 3.1 Native rename/delete adapters (SDK, app-server) and `PATCH`/`DELETE /api/v1/agents/{uid}/sessions/{id}`
- [ ] 3.2 Conversation rename/delete through the native-session port, index row with it
- [ ] 3.3 Spec sync for C

## 4. Backend — terminal (B)

- [ ] 4.1 Terminal adapters + `POST /api/v1/fs/terminal` + `GET /api/v1/fs/terminals`
- [ ] 4.2 Session-in-use detection (process arguments) and Codex active-writer mapping; channel refusal reply
- [ ] 4.3 Spec sync for B (daemon, chat, channels)

## 5. Frontend

- [ ] 5.1 Conversations list and Agent › Sessions list (shared row); delete detail pages and web chat components
- [ ] 5.2 Open in terminal (split button, Copy command, busy dialog), rename / delete
- [ ] 5.3 Settings › General: preferred terminal, hand-off agent
- [ ] 5.4 Hand-off button: start the default agent in the terminal; delete the draft path
- [ ] 5.5 i18n (en + zh), codegen, knip

## 6. Close

- [ ] 6.1 web-ui spec sync; e2e specs
- [ ] 6.2 Docs (en + zh): guides, architecture, ADRs, Claude `cleanupPeriodDays` note
- [ ] 6.3 Archive the change (`--skip-specs`)
