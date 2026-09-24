## Context

A turn already carries files end to end. A channel downloads each one into
`~/.coffer/channel-media` and hands the orchestrator an `Attachment(path, mime,
filename)`; `TurnOrchestrator._begin_turn` persists an `AttachmentBlock` per
file after the user text; `turn_runner._attachments_from_history` reads them
back for the adapter; the Claude and Codex adapters, the document extractor and
the transcription seam do the rest
([Channel Attachments](../../../docs/decisions/channel-attachments.md),
[chat architecture](../../../docs-site/architecture/chat.md)). The web page
lacked only an entrance: its send was a JSON body with one `text` field.

So this change adds an entrance and reuses everything behind it. The decisions
are where the bytes land, how they travel from the browser, what bounds them,
and what the page shows.

## Decisions

### An upload call that returns an opaque id; the send carries ids

`POST /api/v1/chat/attachments` takes one multipart file and returns
`{id, filename, mime, size}`; `POST .../messages` gains `attachment_ids`.
Rejected: multipart on the send itself — it would make the one send route two
content types, re-upload every file on a retry, and give the composer no
per-file progress or failure; and base64 inside the JSON send — a third larger
and the same all-or-nothing. The separate call is also what lets a draft attach
before its conversation exists (the conversation is created on the first
send). Argued in full in the new ADR
[Chat Attachment Uploads](../../../docs/decisions/chat-attachment-uploads.md).

The id is `uuid4().hex`; the store only joins an id into a path after checking
it is exactly 32 hex characters, so a client-sent value is never a path. The
id is reusable until the file is pruned, which keeps a re-send of the same
files cheap.

### A sibling directory, `~/.coffer/chat-media`, with the channel media's retention

The bytes land beside `channel-media`, not in it. Rejected: sharing
`channel-media` — the filesystem reference, the ADR and the channels spec all
say that directory holds what channels downloaded, and a reader cleaning it up
should not find the page's uploads there; and a generalised media store both
kinds write through — channels write from three transports with their own
naming and there is nothing to gain from moving them. What the two directories
share is the **rule**, so the rule moves: `files_to_prune` and
`MEDIA_RETENTION_DAYS` go from `domain/channel/` to the kind-agnostic
`domain/retention.py`, the stat/unlink sweep from `infrastructure/channel/` to
the kind-agnostic `infrastructure/media_retention.py`, and `RetentionService`
takes one sweep per directory keyed by the name the prune reports
(`channel_media`, `chat_media`) instead of one callable. This is the second
consumer the "extract only after the second feature needs it" principle waits
for.

The directory resolves from `HOME`, exactly as `channel-media` does; there is
no new environment variable (the tests redirect `HOME`).

Each upload is two flat files: the bytes as `<id><ext>` (so a path-native
agent still sees `.pdf` or `.png`) and `<id>.json` with the display name, type,
size and stored file name. Flat, so the existing per-file mtime sweep applies
unchanged; the record is written after the bytes, so an id never resolves to a
half-written file.

### Bounds: 20 MB a file, ten a message, types an agent can use

20 MB is the ceiling a hand-passed document already has in Coffer — the
knowledge upload's `MAX_UPLOAD_BYTES` and Telegram's bot-API download cap — so
a file attached on the page and one sent from the phone meet the same limit.
A request declaring a larger body (plus a small multipart allowance) is refused
before it is read, and the form is parsed with room for one file. Ten
attachments a message bounds the send body and a turn's materialisation. An
image is stored under the type its bytes prove, and Claude Code receives one
inline only when it is at most 5 MB once base64-encoded; a larger or
unrecognised image reaches it as a path.

Accepted types are decided by a pure function (`upload_mime` in
`domain/chat/attachment.py`): images, audio and documents by declared type,
then by a fixed extension table, and anything whose bytes are UTF-8 without a
NUL as text. The table is fixed rather than the stdlib `mimetypes`, which reads
the host's mime files and would make the same upload pass on one machine and
fail on another. Video, archives and other binaries are refused: neither agent
can use them from a turn. The document mime set moves from
`infrastructure/chat/document_extract.py` to the same domain module, so what
the upload calls a document and what the extractor extracts are one list.

### The turn path does not change

The route resolves ids to `Attachment`s and calls `enqueue_message(...,
attachments=...)` — the call a channel makes. Persistence as references,
re-materialisation from history, per-agent materialisation, document
extraction and transcription are therefore the same code for both entrances,
and a restarted daemon runs a queued or retried turn with the same files. A
queued web message keeps its attachments through a queue reorder (the existing
"Reconcile a replaced queue against existing entries" rule).

A message with files and no text persists the stand-in text a channel's
uncaptioned photo gets (`attachment_note`, moved from `application/channel` to
`domain/chat/attachment.py` so both kinds use it), because an agent request
cannot carry an empty text block; the conversation it opens is named after the
files, as a channel's is.

Uploads are not written to the audit log: a turn's record lives in its
conversation, not the audit log ("Keep a turn's record in its conversation, not
the audit log"), and an upload is the first half of a turn.

Chat ships no CLI (a known gap recorded in the spec's Purpose), so there is no
`coffer chat attach`; the upload route is REST only, like the rest of chat.

### What the page shows

The composer holds per-file state (`uploading`, `ready`, `failed` with the
translated reason) and uploads each file the moment it is added, through the
shared `call()` helper with a `FormData` body. The uploading state is a
spinner, not a percentage: a percentage needs `XMLHttpRequest`, a second
transport beside `call()` that `.agents/frontend.md` §4 rules out, and a 20 MB
file crosses loopback in well under a second. Send is disabled while any chip
is uploading or failed, so nothing is dropped silently; a failed chip is
removed by the owner.

In the thread, a user message's `attachment` blocks render through one
`AttachmentChip` component shared with the composer (the thread shows name and
type, the composer name, size and remove). The optimistic echo carries the
attached files' names and types, so the chips appear before the row lands; an
echo of an attachment-only message matches its row by those names, since its
persisted text is the stand-in the page never saw. After a reload the chips
come from the persisted references, so they read the same whichever surface
sent the file. The page shows no image preview: that would need a route
serving the bytes back, and the path stays inside the daemon.

## Risks / Trade-offs

- An upload that is never sent stays on disk until the 30-day sweep. Bounded
  by the per-file ceiling and the owner being the only client.
- A reference outlives its file after 30 days; a later turn degrades to "could
  not be read", as for channel media.
- Retry after a failed turn re-sends the message text only, so the retried turn
  does not carry the files again; the owner re-attaches them. The page holds no
  upload ids for a persisted row, and carrying them would put ids on the wire
  that the thread otherwise never needs.
