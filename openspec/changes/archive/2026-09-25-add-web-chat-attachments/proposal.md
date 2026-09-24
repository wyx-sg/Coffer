## Why

The web Chat page's composer takes text only. A screenshot, a PDF or a log file
reaches a conversation only when the owner sends it from a phone over a
channel, although every turn already knows how to carry files: a channel
downloads them, the user message persists a reference to each, and every agent
adapter materialises the reference in its own native shape (images inline for
Claude Code, paths for Codex, documents extracted to text, audio transcribed
when configured). The desktop is where most of those files are, and the page
had no way to hand one over.

## What Changes

- **Upload route.** `POST /api/v1/chat/attachments` (multipart, one file per
  call) stores the bytes under `~/.coffer/chat-media` and returns an opaque id
  with the file's display name, type and size. It is bounded: at most 20 MB
  (`ATTACHMENT_TOO_LARGE`, 413, naming the limit), and only images, audio,
  documents and UTF-8 text are accepted (`ATTACHMENT_TYPE_UNSUPPORTED`, 415).
  The local path never reaches the wire.
- **Send with attachments.** `POST /api/v1/chat/conversations/{id}/messages`
  takes `attachment_ids` (at most ten). They resolve to the stored files and
  go through the same seam a channel's media does: persisted on the user
  message as attachment references after its text, re-materialised from
  history by the turn task, and materialised per agent by the adapters. A
  message may carry files and no text; it is persisted with the same short
  stand-in a channel's uncaptioned photo gets. An id that names no stored
  upload is refused (`ATTACHMENT_NOT_FOUND`, 422) and nothing is persisted or
  queued.
- **Retention.** `~/.coffer/chat-media` is pruned on the retention cadence by
  the same 30-day mtime rule as `~/.coffer/channel-media`; a full prune reports
  it as `chat_media`. The age rule moves to the kind-agnostic retention module
  and the sweep to a kind-agnostic infrastructure module, shared by both
  directories.
- **Composer.** An attach button, drag-and-drop onto the composer, and pasting
  images add files. Each shows as a chip with its name, size and a remove
  control, and states for uploading and failed (with the reason). Send waits
  while any upload is in flight or failed.
- **Thread.** A user message's attachments render as chips (name and type) —
  the optimistic echo of a just-sent message included — and read the same
  after a reload, because they come from the persisted references.
- **Docs.** A new ADR, `chat-attachment-uploads`, records the upload decision;
  the chat guide, the chat architecture page, the filesystem reference and the
  generated REST reference describe the feature.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `chat`: adds the upload route, attachments on a web send, the chat-media
  prune, and the composer and thread behaviour on the Chat page.

## Impact

- Backend: `domain/chat/attachment.py` (limits, accepted types, the stand-in
  text), `domain/chat/errors.py`, `domain/retention.py` (the media age rule),
  `application/chat/attachments.py` + a `ChatMediaStore` port,
  `infrastructure/chat/media_store.py`, `infrastructure/media_retention.py`,
  `application/retention_service.py` (one sweep per media dir), the chat routes
  and wiring.
- Contract: `openspec/specs/chat/contracts/api.openapi.yaml` (new path and
  `ChatAttachmentOut`, `SendMessageRequest.attachment_ids`); regenerated
  frontend types.
- Frontend: the composer, a shared attachment chip, the send path and the
  optimistic echo, en/zh strings.
- Filesystem: new `~/.coffer/chat-media/` directory.
