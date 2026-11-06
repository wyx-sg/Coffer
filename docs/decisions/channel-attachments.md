# Channel Attachments Are Saved Files, Handed to Every Agent by Path

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: spec channels ("Hand inbound photos and files to the agent", "Hand inbound attachments to the turn as references", "Transcribe inbound voice only when the user opted in", "Download the media a thread's messages carry");
spec chat ("Transcribe audio attachments when transcription is configured");
[Channels Are Thin Transport Adapters](channel-adapter-framework.md), [Driving Agents Through the SDK and App-Server](driving-agents-through-sdk-and-app-server.md),
[Audit and Retention](audit-and-retention.md), [Speech-to-Text Settings](internal-engine-settings.md);
research [im-agent-bridges](../research/im-agent-bridges.md);
PRs #241, #265, #268, #719

## Context

The owner sends photos, screenshots, PDFs, spreadsheets and voice notes from a
phone and expects the agent to use them ("here's the new time, change the
invitation"). Every platform delivers these as an auth-gated file the
transport must download; a URL alone is useless to the agent.

Both agents Coffer drives run on the owner's machine with their own file tools:

- **Claude Code** (Claude Agent SDK) reads images and PDFs with its `Read`
  tool, and can run any converter installed on the machine for Office files.
- **Codex** (`codex app-server`) is path-native: it opens files with its own
  tools and has no inline-image path over the RPC Coffer uses.
- **Neither can hear audio.**

Coffer's principle is to be as lean as possible: what an agent can do itself,
Coffer does not do. Until 2026-11-06 Coffer did more than hand over the file:
it converted documents (PDF, Word, PowerPoint, Excel, RTF, EPUB, CSV) to text
with MarkItDown for every agent and folded the text into the prompt, and it
inlined JPEG/PNG/GIF/WebP images as base64 blocks for Claude Code, sniffing
the bytes to keep a mislabelled file from failing the turn. Each of those was
a code path, a dependency surface and a set of size and format limits to keep
right, for work the agents already do.

A survey of other agent front ends (aider, Cline, OpenHands, Continue, Open
Interpreter and Goose inline base64; Codex and the CLI bridges such as
cc-connect and Claude-to-IM hand over paths) found both shapes in use. The
inline ones are chat UIs over an API; the path ones drive an agent that has
tools, which is what Coffer does.

## Options Considered

### Option A — Path only, for every agent (chosen)

How it works: the transport saves each file under
`~/.coffer/content/channel-media` and puts `InboundAttachment(path, mime,
filename)` on the envelope. Files carried by a fetched thread or a quoted
message are downloaded the same way and join the turn. The turn carries the
references, never the bytes. Each adapter adds one `[Attachments]` block to the
prompt naming every file by name, type and saved path
(`attachment_note` in `infrastructure/chat/adapter_support.py`); a file that is
gone says so. The one exception is voice: it is transcribed to text when the
owner has configured a transcription connection and model, because neither
agent can hear; otherwise the audio file is handed over like any other.

Pros: one code path for both agents; no document parser, image sniffing or
inline-size limit in Coffer; the agent reads a document the way it reads any
file, with its own tools and judgement (a page range of a long PDF rather than
all of it in the prompt); nothing in the prompt grows with the file.

Cons: Claude spends one tool call to look at a picture it could have been shown
directly, so a photo turn is a few seconds slower. An Office file is only as
readable as the converters on the machine; the agent may have to install or
run one.

Wins because both agents already read files, and the cost is one tool call,
not a missing capability.

### Option B — Per-agent materialisation: text for documents, inline images for Claude (the design replaced)

How it works: documents are converted to text for every agent and folded into
the prompt (MarkItDown, lazily imported and run off the event loop); a failed
conversion falls back to the path. Claude Code gets a base64 `image` block for
the four formats the Messages API accepts inline; anything else, and every file
for Codex, is a path.

Pros: Claude sees a picture without a tool call; a path-native agent gets a
binary document's text without converting it.

Cons: two materialisation paths plus a converter to keep correct; MarkItDown
and its parsers stay in the frozen daemon for the channel's sake; a large
document fills the prompt whether or not the agent needs it; an image whose
bytes do not match its declared type failed the whole Claude turn until
sniffing was added. All of it duplicates what the agents do themselves.

Loses to the lean principle: it buys a tool call's worth of latency with code
Coffer has to own.

### Option C — Inline base64 for every agent

How it works: every attachment travels as encoded bytes in the turn.

Pros: the agent never has to open a file.

Cons: Codex has no inline path over app-server, so it would still need the
path; a 3–5 MB photo is 4–7 MB of base64 per turn; documents still need
conversion.

Loses because it does not work for Codex and costs the most.

### Option D — Anthropic Files API (`file_id`)

How it works: upload once, reference by id across turns.

Pros: efficient for large files re-referenced many times.

Cons: stateful and provider-locked; unavailable on Bedrock and Vertex; not a
documented path through the SDK's streamed input. It helps Claude only.

Loses because it solves a scale problem channel sends do not have, for one
agent.

## Decision

Inbound files are saved under `~/.coffer/content/channel-media`, and the turn
carries a reference (path, mime, filename) per file, never the bytes. Every
agent is handed every attachment as its saved path in one `[Attachments]`
block of the prompt; the agent opens it with its own tools. Voice is the one
thing Coffer converts: it is transcribed when the owner opted in. Files older
than the `attachments` retention window (30 days by default) by mtime are
pruned.

Rules a future change must respect:

- Bytes never enter the history database or the prompt.
- Coffer does not convert, inline or summarise a file an agent can open itself;
  a new modality joins as a new path, or, like voice, as a conversion only when
  no agent can take it at all.

## Consequences

- A new agent gets attachments with no adapter work beyond the shared
  `attachment_note`.
- MarkItDown is imported only by the knowledge converter (import-linter
  Contract 7 in `backend/pyproject.toml`).
- A reference whose file was pruned is named as unreadable; the owner resends
  from the phone.
- Enforced by: `attachment_note` in `infrastructure/chat/adapter_support.py`;
  `attachments_block` in `domain/chat/attachment.py`; `_build_content` in
  `infrastructure/chat/claude_sdk_agent.py`; `codex_agent.py`; the
  transcription seam in `infrastructure/chat/transcribe.py`;
  `domain/retention.py` and `infrastructure/media_retention.py`.
