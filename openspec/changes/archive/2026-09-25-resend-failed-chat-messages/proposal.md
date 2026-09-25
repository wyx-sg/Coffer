## Why

Retrying a failed Chat turn re-sent only its text: the web page called send again with the message's words, and the files the message carried were dropped without a word. The page cannot re-send them on its own, because the wire exposes an attachment's name and type but not the stored file behind it. Separately, on the draft surface a conversation is created before its first message is sent, so when the daemon refused that first message (for example `ATTACHMENT_NOT_FOUND`) the draft's text and attachment chips vanished along with the draft.

## What Changes

- New `POST /api/v1/chat/conversations/{id}/messages/{message_id}/resend`: rebuilds a persisted user message — text and every attachment reference — and queues it exactly as a send does. A file the 30-day media sweep has deleted refuses the resend with `ATTACHMENT_EXPIRED` (410) naming the file; an id that is not a user message of the conversation is `MESSAGE_NOT_FOUND` (404).
- The web Retry uses that route for a persisted message, and re-sends text plus upload ids for one whose row has not landed yet. A refused send offers no Retry, so Retry never falls back to an older, unrelated message.
- A draft whose conversation was created but whose first message was refused hands its text and ready attachment chips to the new conversation's composer and shows the refusal in its thread.

## Capabilities

### New Capabilities

### Modified Capabilities
- `chat`: "Show a failed turn as one inline banner with Retry" and "Create the conversation on the first send" gain the rules and scenarios above.

## Impact

- Backend: `application/chat/{attachments,service,ports}.py`, `infrastructure/chat/media_store.py`, `surfaces/http/chat/turn_routes.py`, two new error codes.
- Contract: `openspec/specs/chat/contracts/api.openapi.yaml` + regenerated frontend types; generated REST reference.
- Frontend: Chat retry and draft send paths (`useChatTurn`, new `useChatSend`, `useChatController`, `Composer`, new `useComposerRestore`).
- Docs: `docs-site/guides/chat.md`, `docs-site/architecture/chat.md`, error-code reference.
