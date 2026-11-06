# A Channel Reply Goes Out as the Agent Wrote It; Coffer Does Not Reshape Tables or Code

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: spec channels ("Shape a reply for what the chat can show", "Tell a channel-driven agent it is on a chat channel");
[A Channel's System Prompt Is a Fixed Channel Note Plus a Reply Style](channel-prompt-fixed-note-and-editable-style.md),
[A Long Channel Reply Is Rewritten Short by the Agent](long-channel-reply-is-rewritten-short.md),
[A Channel Reply Names Its Files, and the Files Follow It](a-reply-names-its-files-and-they-follow-it.md);
PR #719

## Context

An agent answers in GitHub-flavoured Markdown, and a chat shows only part of it.
SeaTalk has no tables (a table arrives as raw pipes in a text message and fails
in a card), and a 200-line log in a phone chat is a wall.

Until 2026-11-06 Coffer ran a structure pass on every finished reply, driven by
two transport capabilities: where `renders_tables` was false, each table became
one bullet per row, and a table past 12 rows or 4 columns kept five rows and
went out whole as a `.csv`; where `max_inline_code_lines` was set (SeaTalk: 30),
a longer fenced block kept three lines and went out whole as a `.log` or
`.diff` file. The pass needed its own Markdown table and fence parser, file
naming, staging and upload.

Meanwhile the channel note already tells the agent what renders on the chat it
is in ("This chat … does NOT render … tables (write one bullet per row)"), the
reply style asks for about eight lines and a full report only as a file, and
the agent can send any file with a `MEDIA:` line. Coffer's principle is to be
as lean as possible: what an agent can do itself, Coffer does not do.

## Options Considered

### Option A — Send the reply as written; tell the agent what the chat renders (chosen)

How it works: the finished reply goes to the platform renderer unchanged. The
only transport-dependent handling left is presentation the agent cannot do: a
`## Details` section is collapsed where the transport collapses it (Telegram)
and sent whole elsewhere, and a reply longer than one message is cut between
messages, never inside a code fence, each part after the first marked `(2/3)`.

Pros: no parser that can misread the agent's Markdown (a table inside a fence,
a pipe in prose); the agent decides how to present data, with the whole answer
in view, instead of Coffer cutting a table at row five; one less file path out
of the turn; a new transport needs only its render notes.

Cons: an agent that ignores the note sends raw pipes to SeaTalk; a long log
stays inline unless the agent chooses to send it as a file.

Wins because the agent already knows what the chat renders and already has a
way to send files, so the rewrite duplicated it.

### Option B — Rewrite tables and long code from capabilities (the design replaced)

How it works: as described in Context.

Pros: a table is readable on SeaTalk even when the agent ignores the note; a
long log never fills the phone screen.

Cons: Coffer owns a Markdown table parser, CSV writer, code-fence parser, file
naming and an upload path; the result can surprise the agent's intent (five
rows kept of a ranking that mattered at row eight); two capabilities every
transport must declare. All of it is work the agent does with one instruction.

Loses to the lean principle.

### Option C — Render tables as images

How it works: draw each table into a PNG and send it as a picture.

Pros: the table keeps its shape on any chat.

Cons: an image renderer in the daemon; the data is no longer copyable or
searchable; the agent can already make a PNG when a picture is what reads best.

Loses for the same reason as B, at a higher cost.

## Decision

A finished channel reply goes out as the agent wrote it. Coffer does not turn
tables into bullets or files, and does not move long code blocks into files;
the channel note tells the agent what the chat renders, and the agent sends a
file itself when a file reads better. Transports keep only the presentation
the agent cannot do: collapsing a `## Details` section where they can, and
cutting a long reply into messages without splitting a code fence.

Rules a future change must respect:

- A rendering limit of a transport is told to the agent in its render notes,
  not fixed by rewriting the reply.
- A transport capability describes what the platform does with a message
  (collapse, edit, upload), never how Coffer should rewrite the agent's text.

## Consequences

- The render notes in each transport's capabilities (`SEATALK_RENDER_NOTES` in
  `infrastructure/channel/seatalk_caps.py`) are the one place to say what a
  chat cannot show.
- `application/channel/reply_shape.py` holds only `split_details`.
- Enforced by: spec channels "Shape a reply for what the chat can show" and
  its scenario "a table goes out as the agent wrote it"
  (`tests/integration/channel/test_reply_shaping.py`).
