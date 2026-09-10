# Persist channel attachments as a reference block, re-materialise from history

> 中文版: [persisted-attachment-reference.zh.md](persisted-attachment-reference.zh.md)

**Status**: Accepted
**Date**: 2026-07-09
**Deciders**: Yuxing Wu
**Related**: spec `channels` (FR-033); supersedes the v1 "defer a persisted
attachment block" decision in [Channel Media](channel-media.md)

## Context

[Channel Media](channel-media.md) stored channel media bytes out-of-band in
`~/.coffer/channel-media` and passed a **this-turn-only** attachment reference
out of band — through `start_turn → run_turn` — **not** as message content. It
explicitly **deferred** a persisted attachment `ContentBlock` for v1, citing the
blast radius (message model, persistence, frontend block rendering, OpenAPI
contract) and the DB-bloat risk of inlining base64.

The consequence Channel Media accepted: an attachment was materialised per turn but
never persisted, so anything that re-reads full history (no session resume) saw
a note, not the image, and the attachment left no trace in the conversation.
FR-033 revisits that decision — the key realisation is that a **reference** block
(path/mime/filename, **no bytes**) removes the DB-bloat objection entirely.

## Decision

**Persist the attachment as a reference `AttachmentBlock` in the user message, and
make that persisted reference the single source of truth for materialising the
turn.**

1. `AttachmentBlock(path, mime, filename, type="attachment")` joins the
   `ContentBlock` union (domain, JSON (de)serialisation, OpenAPI contract). It
   carries a reference only — **never the bytes**.
2. The orchestrator persists the turn's attachments into the user message content
   (after the `TextBlock`), even for an attachment-only turn.
3. The turn task **derives** the attachments handed to `adapter.run_turn` by
   reading them back from the **last user message in history** — not from a param
   threaded down from the orchestrator. Since history is fetched after the user
   message is persisted, `history[-1]` *is* the current turn's user message. This
   makes "re-materialise from history" literal, keeps every adapter **unchanged**
   (they still receive `attachments: Sequence[Attachment]` and materialise per
   model as in Channel Media), and works after a daemon restart (history is durable).
4. **Web** renders the reference as a compact `📎 filename · mime` chip on the
   user bubble. The local **path is never emitted to the wire** (the wire
   `ContentBlock` exposes `filename`/`mime`, not `path`) — a leak/security line.
5. **Replay scope is within the current conversation only** — the persisted
   reference materialises *this* conversation's turn. No cross-session /
   agent-switch full-history replay.
6. **Retention**: a 30-day mtime prune of `~/.coffer/channel-media` runs on the
   existing retention cadence (no size cap). The decision (which files are old
   enough) is a pure domain helper; the stat/unlink sweep is infrastructure,
   injected into `RetentionService` at composition root.

## Alternatives considered

- **Keep Channel Media as-is (this-turn-only, out-of-band param)** — simplest, but the
  attachment is invisible in the web UI and lost after a daemon restart mid-turn.
  Rejected: FR-033 exists precisely to make the attachment durable + visible.
- **Inline base64 in a persisted block** — the DB-bloat case Channel Media rejected;
  still rejected. The reference block gets the history/visibility benefit without
  the bytes.
- **Emit the local path to the wire** — would let the web fetch/preview, but leaks
  an absolute host path to any API client. Rejected for security; a filename/mime
  chip is enough for the web's needs.
- **A media-serving endpoint + thumbnails** — richer web preview, but a much
  larger surface (auth, range serving, cache). Deferred; the chip suffices.
- **Reference-counted media retention (delete only unreferenced files)** — avoids
  deleting a file a live conversation still points at, but needs a scan of every
  conversation's blocks per sweep. Not worth it: bytes are re-downloadable and a
  dead reference degrades gracefully, so a plain mtime age prune is sufficient.

## Consequences

- The attachment lives in history and survives a daemon restart; the persisted
  reference is the one source of truth for materialisation.
- Adapters are untouched — the seam moved (history read-back instead of a param),
  not the adapter contract. The modality-agnostic property from Channel Media holds.
- Old text-only message rows deserialise unchanged (schemaless JSON content, no
  migration); `block_from_dict` gained one `attachment` case.
- Media bytes are bounded by the 30-day prune instead of accumulating forever
  (closing the retention gap Channel Media left open).
- Superseded bullet in Channel Media: its "defer a persisted attachment block" alternative
  and its "not persisted as message content" consequence are replaced by this ADR.
