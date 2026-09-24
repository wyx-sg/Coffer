# Channel Attachments: Bytes on Disk, a Reference in the Message, Materialised per Agent at Send

**Status**: Accepted
**Date**: 2026-07-09
**Deciders**: Yuxing Wu
**Related**: spec channels ("Hand inbound photos and files to the agent", "Persist inbound attachments as references", "Give documents to every agent as extracted text", "Transcribe inbound voice only when the user opted in", "Download the media a thread's messages carry");
spec chat ("Re-materialise attachments from persisted history", "Extract document attachments to text", "Transcribe audio attachments when transcription is configured");
[Channels Are Thin Transport Adapters](channel-adapter-framework.md), [Driving Agents Through the SDK and App-Server](driving-agents-through-sdk-and-app-server.md),
[Audit and Retention](audit-and-retention.md), [Internal Engine Settings](internal-engine-settings.md),
[Chat Attachment Uploads](chat-attachment-uploads.md) (the web Chat page's entrance to the same path);
PRs #241, #265, #268

## Context

The owner sends photos, screenshots, PDFs, spreadsheets and voice notes from a
phone and expects the agent to use them ("here's the new time, change the
invitation"). Every platform delivers these as an auth-gated file the
transport must download; a URL alone is useless to the agent.

The two agents take files differently:

- **Claude Code**, driven through the Claude Agent SDK, accepts an inline
  base64 `image` content block in the user turn — the model sees the picture
  directly. The Messages API accepts only JPEG, PNG, GIF and WebP inline; any
  other image format fails the whole turn.
- **Codex**, driven through `codex app-server`, has no inline-image path over
  the RPC Coffer uses; it is path-native and opens files with its own tools.
- **Neither can hear audio**, and a path-native agent handed a binary PDF
  cannot read it.

A survey of other agent front ends (aider, Cline, OpenHands, Continue, Open
Interpreter and Goose inline base64; Codex and CLI bridges hand over paths)
found no single mechanism that fits both agents.

And the bytes have a cost: a 3–5 MB photo is 4–7 MB of base64. Storing that in
the chat database would bloat it and resend it on every history read, yet an
attachment that leaves no trace in the conversation is invisible on the web
Chat page and lost after a daemon restart.

## Options Considered

### Option A — Bytes in a Coffer-managed directory; an `AttachmentBlock` reference persisted in the user message; each agent materialises the reference its own way at send time (chosen)

- **Download.** The transport saves each file under `~/.coffer/channel-media`
  and puts `InboundAttachment(path, mime, filename)` on the envelope
  (`domain/channel/envelopes.py`). Files carried by a fetched thread or a
  quoted message are downloaded the same way and join the turn.
- **Persist a reference.** The orchestrator writes the user message as a text
  block followed by one `AttachmentBlock(path, mime, filename)` per file —
  never the bytes (`application/chat/turn_orchestrator.py`).
- **Re-materialise from history.** The turn task reads the attachments back
  from the last `USER`-role message in history, searched backwards
  (`_attachments_from_history` in `application/chat/turn_runner.py`), rather
  than having them threaded down as a parameter. The persisted reference is the
  single source of truth, so a turn run after a restart materialises the same
  files.
- **Materialise per agent**, in each adapter:
  - *Voice* is transcribed to text when the owner has configured a
    transcription connection and model; otherwise the audio file is handed
    over like any other file (`infrastructure/chat/transcribe.py`,
    `infrastructure/llm/transcription.py`). Transcription is the one place
    user content leaves the machine, so it is off until chosen.
  - *Documents* (PDF, Word, PowerPoint, Excel, RTF, EPUB, CSV) are converted
    to text for **every** agent and folded into the prompt
    (`infrastructure/chat/document_extract.py`, MarkItDown, imported lazily
    and run off the event loop); a failed conversion falls back to handing
    over the file.
  - *Images*: Claude Code gets a base64 `image` block for JPEG/PNG/GIF/WebP,
    built in memory for the outbound request only
    (`infrastructure/chat/claude_sdk_agent.py`); Codex gets the path in the
    prompt (`infrastructure/chat/codex_agent.py`).
  - *Anything else*, and any image format Claude cannot take inline, becomes a
    text pointer to the saved path.
- **The wire shows filename and mime only.** The API's content block exposes
  `filename` and `mime` for a chip on the web page; the local path never
  leaves the daemon (`surfaces/http/chat/conversation_routes.py`).
- **Retention.** `~/.coffer/channel-media` is swept on the retention cadence:
  files whose mtime is more than 30 days old are deleted
  (`files_to_prune` in the kind-agnostic `domain/retention.py` decides,
  `infrastructure/media_retention.py` does the I/O, bound into
  `RetentionService` as one sweep per media directory). There is no size cap and no
  reference check.

Pros: the database holds kilobytes per attachment, not megabytes; each agent
gets its best native form; the attachment is visible in the conversation on
every surface and survives a restart; a new modality is a new `mime`, not a new
schema.

Cons: a reference can outlive its file — after 30 days, or if the owner clears
the directory — and a later re-read then degrades to "could not be read". Only
the current turn's attachments are materialised; an earlier turn's image
reaches the agent only through its own resumed session. Absolute paths live in
the database, so a vault moved to another home directory would carry stale
references.

Wins because it gets history, visibility and restart-safety without paying for
bytes in the database, and adapts per agent where no common mechanism exists.

### Option B — Out-of-band, this turn only (no persisted block)

How it works — the design first shipped (PR #241): the bytes go to disk and
the attachment references travel alongside `start_turn` into `run_turn` for
that one turn; the persisted user message keeps only the caption or a short
"(sent an image)" note.

Pros: no change to the message model, persistence or the API contract.

Cons: the attachment was invisible on the web Chat page, lost if the daemon
restarted mid-turn, and anything reading history later saw a note, not a file.
Its reason for existing — keeping bytes out of the database — did not require
keeping the *reference* out too.

Loses because a reference block removes the database objection and gains
durability and visibility; it was replaced five days later (PR #268).

### Option C — Inline base64 persisted in the message

How it works: an attachment block carries the encoded bytes and is stored with
the message.

Pros: the conversation is self-contained; no files to manage or prune.

Cons: megabytes per photo in SQLite, reloaded on every history read; the web
page would pull them over the wire; and the bytes would still need
per-agent handling, since Codex cannot use them.

Loses on database size and on still needing per-agent materialisation.

### Option D — Path only, for every agent

How it works: every agent gets "the user attached X, saved at /path".

Pros: one code path; no encoding.

Cons: a vision model is made to call a tool to see an image it could have been
shown directly, and a path-native agent handed a binary document cannot read
it at all.

Loses because it serves neither agent at its best.

### Option E — Anthropic Files API (`file_id`)

How it works: upload once, reference by id across turns.

Pros: efficient for large files re-referenced many times.

Cons: stateful and provider-locked; unavailable on Bedrock and Vertex; not a
documented path through the SDK's streamed input, and file scoping under
subscription auth is unclear. It helps Claude only.

Loses because it solves a scale problem channel sends do not have, for one
agent.

### Option F — Store bytes in the database as BLOBs

How it works: a table of attachment bytes keyed by id; the message references
the id.

Pros: one store, backed up and deleted with the conversation.

Cons: the same size problem as Option C in a different table, plus every
consumer must stream bytes out of SQLite to disk anyway, since Codex and the
document converter need a path.

Loses because the agents consume files, so the file is the natural store.

## Decision

Inbound files are saved under `~/.coffer/channel-media`. The user message
persists an `AttachmentBlock(path, mime, filename)` per file and never the
bytes. Each turn re-materialises its attachments from the last user message in
history, and each agent adapter turns them into its native form: voice is
transcribed when opted in, documents become text for every agent, supported
images are inlined as base64 for Claude Code and handed as paths to Codex, and
everything else is a path pointer. The API exposes an attachment's filename
and mime, never its path. Files older than 30 days by mtime are pruned.

Rules a future change must respect:

- Bytes never enter the chat database.
- The local path never reaches the wire.
- Materialisation is per agent and lives in the adapter; the block stays
  agent-neutral.

## Consequences

- A new agent decides its own materialisation in its adapter; nothing in the
  message model changes.
- Old text-only message rows needed no migration; the block is one more case
  in the schemaless JSON content.
- A reference whose file was pruned degrades to a text note on later reads;
  bytes are re-sendable from the phone.
- Enforced by: `AttachmentBlock` in `domain/chat/message.py`;
  `turn_orchestrator.py` and `turn_runner.py` in `application/chat/`; the two
  adapters and the transcription and extraction seams in
  `infrastructure/chat/`; `domain/retention.py` and
  `infrastructure/media_retention.py`.
