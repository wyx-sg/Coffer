# ADR-038: Channel media — reference in the DB, materialise per agent at send

> 中文版: [ADR-038-channel-media.zh.md](ADR-038-channel-media.zh.md)

**Status**: Accepted
**Date**: 2026-07-04
**Deciders**: Yuxing Wu
**Related**: spec `009-channels` (FR-020); builds on [ADR-014](ADR-014-channel-adapter-framework.md) (channel adapter framework)

## Context

A channel-driven agent must be able to receive the photos and files the owner
sends from a phone (the motivating case: "here's a screenshot of the new time,
change the invitation"). Before this, `TelegramAdapter._dispatch` read only
`message.text`, so any non-text message reached the core as an empty envelope and
was rejected — the agent never saw the image.

The two supported agents consume images differently:

- **Claude Code** (driven through the Claude Agent SDK's stream-json input) accepts
  an inline `image`/`document` **content block** (base64) in the user turn — the
  documented, native mechanism for a programmatic driver. The model sees the image
  directly, no tool call required.
- **Codex** (driven through its app-server RPC) has **no** inline-image path; it is
  path-native (`-i <path>` + a `view_image` tool). An Anthropic image block is
  meaningless to it.

A survey of how established agents feed images (aider, Cline, OpenHands, Continue,
Open Interpreter, Goose all inline base64; Codex and CLI-process bridges hand off
paths) confirmed there is **no single mechanism** that fits both — the robust
design must adapt per agent.

The tension: inline base64 is the native mechanism, but a 3–5 MB photo becomes
~4–7 MB of base64 that, if persisted in the message content, bloats the chat DB
and is re-sent on every turn.

## Decision

**Store bytes out-of-band; keep only a reference in the chat DB; materialise per
agent at send time.**

1. The transport downloads each attachment (`getFile` → download) to a
   Coffer-managed media dir (`~/.coffer/channel-media`). The inbound envelope
   carries an `InboundAttachment(path, mime, filename)`.
2. The bytes **never** enter the chat DB. The persisted user message keeps the
   caption (or a short "(sent an image: …)" note when there is none). The
   attachment references travel **out-of-band, for this turn only**, through
   `start_turn → run_turn` — not as message content — so the frozen message model,
   persistence, and the web/OpenAPI contract are untouched.
3. Each agent adapter materialises the reference in its own native shape:
   - **Claude Code** reads the file at send time, base64-encodes it **in memory**,
     and inlines an `image` block (or `document` for PDF); a non-vision file
     becomes a text pointer to its path. The base64 exists only in the outbound
     request.
   - **Codex** receives the on-disk path appended to the prompt (its native model).

## Alternatives considered

- **Inline base64 as a new `ContentBlock` persisted in the message** — the most
  "native" (attachment lives in history, shows in the web UI), but ripples across
  the message model, persistence, the frontend block renderer, and the OpenAPI
  contract, and either bloats the DB (base64) or needs a path-ref block anyway.
  Rejected for v1: the ripple and DB cost outweigh the history-replay benefit,
  which Claude Code's session resume already covers within a conversation.
- **Anthropic Files API (`file_id`)** — a scale optimisation for large assets
  re-referenced across many turns, but stateful, provider-locked, unavailable on
  Bedrock/Vertex, and not documented through the SDK stream-json path (Claude
  Code's subscription auth makes `file_id` scoping unreliable). Overkill for
  one-shot channel sends. Deferred until a concrete need.
- **Save-to-disk + path note only, for every agent** — simplest, but fobs a
  vision agent off with a `Read` tool call when it could see the image natively.
  Rejected: not robust, and the research showed inline is the standard for
  vision-capable agents.

## Consequences

- History stays small; no base64 in the DB; the frozen message/persistence/web
  seams are untouched.
- The design is modality-agnostic: audio, zip, etc. are the same reference; a new
  type is a new `mime`, not a new schema. A future **audio-native** agent is one
  more `run_turn` branch (inline audio block vs. transcribe-then-text vs. hand off
  the path), keyed on the agent's capability — this is the seam spec `009` FR-022
  (voice) builds on.
- An attachment is materialised per turn; it is not persisted as message content,
  so a follow-up that re-reads full history (no session resume) sees the note, not
  the image. Acceptable for v1 — Claude Code's resume retains it in-session.
- Bytes accumulate under `~/.coffer/channel-media`; retention/cleanup is a
  follow-up (not gated here).
