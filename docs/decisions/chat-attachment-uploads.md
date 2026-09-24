# The Chat Page Uploads a File First and Sends Its Id, Into a Sibling Media Directory

**Status**: Accepted
**Date**: 2026-09-25
**Deciders**: Yuxing Wu
**Related**: spec chat ("Upload a file for a web message", "Send uploaded files with a web message", "Prune uploaded chat media on the retention cadence", "Attach files from the Chat page composer", "Show a message's attachments in the thread");
[Channel Attachments](channel-attachments.md) (the reference-in-the-message design this reuses),
[Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md) (the send is fire-and-return),
[Audit and Retention](audit-and-retention.md) (the age sweep)

## Context

A turn already carries files end to end. A channel downloads each file,
the orchestrator persists an `AttachmentBlock(path, mime, filename)` after the
user text, the turn task reads the blocks back from history, and each agent
adapter materialises them in its own shape ([Channel
Attachments](channel-attachments.md)). The web Chat page had no entrance to
that path: its send was a JSON body with one `text` field, and a screenshot on
the desktop reached a conversation only by being sent from the phone.

Three things constrain how the browser hands a file over:

- **The send is fire-and-return and one JSON body.** `POST …/messages` starts
  or queues a turn and answers `202` at once; every client, and the channel,
  shares it.
- **A draft has no conversation yet.** The page creates the conversation on
  the first send, so a file attached to a draft has no conversation to belong
  to when it is attached.
- **The agents need a path.** Codex and the document extractor open a file;
  only Claude Code's images are inlined, and those are read from a path at
  send time. The bytes have to be on disk before the turn runs.

## Options Considered

### Option A — A separate upload call that returns an opaque id; the send carries ids; bytes in `~/.coffer/chat-media` (chosen)

`POST /api/v1/chat/attachments` takes one multipart file, checks its size and
type, writes it under `~/.coffer/chat-media` as `<id><ext>` beside an
`<id>.json` record (name, type, size), and answers `{id, filename, mime,
size}`. `POST …/messages` gains `attachment_ids`; the route resolves each id to
an `Attachment` and calls the same `enqueue_message(…, attachments=…)` a
channel calls. The directory is pruned by the same 30-day mtime rule as
`channel-media`, one sweep per directory.

Pros: the send stays one small JSON body with one content type. Each file has
its own request, so the composer shows each one uploading or failed and
refuses the send while any is — nothing is dropped silently. A draft uploads
before its conversation exists. Everything after the route is the channel's
code: persistence as references, re-materialisation from history, per-agent
materialisation, document extraction, transcription. The id is opaque and
checked to be 32 hex characters before it names a file, so no client value is
ever a path.

Cons: two round trips per file, and an upload that is never sent lingers until
the 30-day sweep. A per-file percentage would need `XMLHttpRequest`, a second
transport beside the shared `call()` helper; the composer shows a spinner
instead, which a 20 MB file on loopback outlasts for well under a second.

Wins because it adds only an entrance: the turn path, the message model and
the adapters do not change, and the composer gets per-file state for free.

### Option B — Multipart on the send itself

How it works: `POST …/messages` accepts `multipart/form-data` with the text and
the files; the route stores the files and enqueues the turn in one request.

Pros: one request per message; no orphaned uploads.

Cons: the one send route gains a second content type that every client and
test must handle; a queued or retried message re-uploads its bytes; the
composer learns about a bad file only when the whole message fails; a draft
must hold the files in memory until its conversation exists.

Loses on per-file feedback and on complicating the route every surface shares.

### Option C — Base64 inside the JSON send

How it works: each file travels as a base64 string in the send body.

Pros: one request, one content type.

Cons: a third larger on the wire, the same all-or-nothing failure as Option B,
and a 20 MB file becomes a 27 MB JSON document parsed in one piece.

Loses for the reasons B does, and heavier.

### Option D — Store web uploads in `~/.coffer/channel-media`

How it works: Option A's upload, into the channel directory, so one prune
covers both.

Pros: one directory, one sweep.

Cons: the filesystem reference, the channels spec and [Channel
Attachments](channel-attachments.md) all say that directory holds what a
channel downloaded; a reader cleaning up after a channel would find the page's
uploads there. The two entrances share a rule, not an owner.

Loses because sharing the rule is enough: the age decision moved to the
kind-agnostic `domain/retention.py` and the sweep to
`infrastructure/media_retention.py`, and each directory is its own sweep.

### Option E — A generalised media store both kinds write through

How it works: one `MediaStore` port with a directory per origin, used by the
channel transports and the upload route alike.

Pros: one store abstraction.

Cons: the three channel transports already name and write their files their
own way and read nothing back through a store; moving them buys nothing the
shared sweep does not already give, and touches every transport.

Loses as churn without a consumer.

## Decision

The web composer uploads each file to `POST /api/v1/chat/attachments`, which
stores it under `~/.coffer/chat-media` and returns an opaque id; a send names
the ids in `attachment_ids`, and the route resolves them to the same
`Attachment` references a channel hands the orchestrator. A file is at most
20 MB, a message carries at most ten, and only images, audio, documents and
UTF-8 text are accepted. `chat-media` is pruned by the 30-day mtime rule
`channel-media` uses.

Rules a future change must respect:

- The upload route returns an id, never a path, and resolves only ids of the
  upload shape.
- Web uploads join a turn through `enqueue_message(…, attachments=…)` — never
  through a path of their own — so both entrances stay one code path.
- The age rule lives once, in `domain/retention.py`; a new media directory is a
  new sweep, not a new rule.

## Consequences

- The Chat page can attach from the desktop; the thread shows a chip per file
  whichever surface sent it, including after a reload.
- A reference whose file was pruned degrades as a channel's does; sending its
  id again is refused as unknown (`ATTACHMENT_NOT_FOUND`).
- Retrying a failed turn resends its text only; the page holds no upload ids
  for a persisted row.
- Chat ships no CLI, so the upload has none either.
- Enforced by: `domain/chat/attachment.py` (bounds, `upload_mime`),
  `application/chat/attachments.py`, `infrastructure/chat/media_store.py`,
  `surfaces/http/chat/attachment_routes.py`, `domain/retention.py`,
  `infrastructure/media_retention.py`, and the `media_sweeps` binding in
  `surfaces/http/app_mcp_composition.py`.
