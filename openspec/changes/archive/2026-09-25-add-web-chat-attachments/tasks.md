## 1. Backend

- [x] 1.1 Domain: upload limits, accepted types (`upload_mime`), display-name cleaning, the shared stand-in text, the document mime set, and three errors (`ATTACHMENT_TOO_LARGE` 413, `ATTACHMENT_TYPE_UNSUPPORTED` 415, `ATTACHMENT_NOT_FOUND` 422)
- [x] 1.2 Move the media age rule to `domain/retention.py` and the sweep to `infrastructure/media_retention.py`; `RetentionService` takes one sweep per media dir (`channel_media`, `chat_media`)
- [x] 1.3 `ChatMediaStore` port, `ChatAttachmentService`, and the file-backed store under `~/.coffer/chat-media`
- [x] 1.4 `POST /api/v1/chat/attachments`; `attachment_ids` on `POST .../messages`, resolved and handed to `enqueue_message` like channel media
- [x] 1.5 Wire the service and the chat-media sweep at the composition root

## 2. Frontend

- [x] 2.1 Upload request helper and composer attachment state (uploading / ready / failed)
- [x] 2.2 Composer: attach button, drag-and-drop, image paste, chips with name/size/remove, Send disabled while uploading or failed
- [x] 2.3 Shared `AttachmentChip` in the thread and the composer; the optimistic echo carries the files
- [x] 2.4 en + zh strings, error-code translations

## 3. Tests

- [x] 3.1 Unit: `upload_mime`, filename cleaning, stand-in text, the service's bounds and resolution
- [x] 3.2 Integration: upload route (201 / 413 / 415 / no path), send with ids (persisted references, adapter receives them, attachment-only, unknown id refused), chat-media prune through `RetentionService`
- [x] 3.3 Vitest: composer attach / paste / failed / uploading, thread chips, echo matching
- [x] 3.4 E2E: attach a file on the Chat page, send, reload, and see its chip in the thread
- [x] 3.5 Every new scenario's test carries its `acceptance("chat", …)` marker

## 4. Contracts and docs

- [x] 4.1 `openspec/specs/chat/contracts/api.openapi.yaml`, frontend codegen
- [x] 4.2 `openspec/specs/chat/data-model.md` and the chat spec's Purpose name both media directories
- [x] 4.3 New ADR `docs/decisions/chat-attachment-uploads.md` + README index; `channel-attachments` points at it
- [x] 4.4 `docs-site/guides/chat.md`, `docs-site/architecture/chat.md`, `docs-site/reference/filesystem.md`; regenerate `docs-site/reference/rest-api.md`

## 5. Close

- [x] 5.1 Run make verify
- [x] 5.2 Archive the change
