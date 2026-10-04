## MODIFIED Requirements

### Requirement: Persist conversations and messages in SQLite
System MUST persist conversations and their messages in SQLite — the history
database, `~/.coffer/runs.db` — as the system of record; they are history of this
machine, never written into the vault, and are not Resources of the kind-agnostic
Resource framework. A
message MUST store its role and an ordered list of content blocks of types
`text`, `tool_use`, `tool_result`, and `attachment` (see "Re-materialise
attachments from persisted history"); assistant messages MUST also store token
usage and the model that produced them when the agent reports one.

A conversation opens under a placeholder title, which System MUST replace with
the text of its first user message (truncated); once the owner has named a
conversation themselves, System MUST NOT overwrite that name — an explicit
rename outranks the generated one. The name MUST come from the part of that
message the person actually wrote, which a client that folds context blocks
into its turns passes down explicitly; the platform MUST NOT recognise any
client's block format itself. Where the person wrote nothing at all (a photo or
a file on its own), the attachment filenames name the conversation; where there
is nothing nameable at all, the conversation keeps its placeholder title rather
than being named after boilerplate.

#### Scenario: reply survives a restart
- **GIVEN** a completed turn,
- **WHEN** the daemon is restarted and the conversation is read back,
- **THEN** the assistant reply is there — the message store, not the live
  stream, is the system of record.

#### Scenario: a conversation the owner named keeps its name
- **GIVEN** a conversation the owner has renamed,
- **WHEN** its first user message arrives,
- **THEN** the conversation keeps the name the owner gave it, and only a
  conversation still under its placeholder title is named from its first
  message.

#### Scenario: token usage is recorded on the assistant message
- **GIVEN** a turn that completes,
- **WHEN** the turn ends,
- **THEN** the assistant message records the turn's token usage.

### Requirement: Upload a file for a web message
The web Chat page MUST be able to hand the daemon a file before sending the
message that carries it. `POST /api/v1/chat/attachments` takes one file per
call, stores its bytes under `~/.coffer/content/chat-media` — never in the chat
database — and answers with an opaque id, the file's display name (its last
path segment), the type it is stored under and its size. The local path MUST
NOT appear in the response. The upload is not tied to a conversation, so a
draft can attach files before its conversation exists. It is bounded: a file
over 20 MB MUST be refused with `ATTACHMENT_TOO_LARGE` (413) whose message
names the limit, and a file that is not an image, audio, a document (PDF, Word,
PowerPoint, Excel, RTF, EPUB, CSV) or UTF-8 text MUST be refused with
`ATTACHMENT_TYPE_UNSUPPORTED` (415). Nothing is stored for a refused upload.
A request that declares a body over the limit (plus a small allowance for the
multipart framing) MUST be refused with the same 413 before its body is read.
An image MUST be stored under the type its bytes prove — PNG, JPEG, GIF or
WEBP — whatever the browser or the filename claimed; a file that claims to be
an image but whose bytes are none of those is stored as a generic file
(`application/octet-stream`), never as an image.
See [Chat Attachment Uploads](../../../docs/decisions/chat-attachment-uploads.md).

#### Scenario: an uploaded file is stored and named by an opaque id
- **GIVEN** a running daemon
- **WHEN** a PNG is uploaded to `POST /api/v1/chat/attachments`
- **THEN** the response is 201 with an id, the file's name, `image/png` and its size
- **AND** the bytes are stored under `~/.coffer/content/chat-media`, and no local path appears in the response

#### Scenario: an oversized upload is refused naming the limit
- **GIVEN** a file larger than 20 MB
- **WHEN** it is uploaded
- **THEN** the response is 413 `ATTACHMENT_TOO_LARGE` whose message names the 20 MB limit
- **AND** nothing is stored

#### Scenario: an upload declaring an oversized body is refused before it is read
- **GIVEN** an upload request whose `Content-Length` is over the 20 MB limit plus the multipart allowance
- **WHEN** it reaches the daemon
- **THEN** the response is 413 `ATTACHMENT_TOO_LARGE`
- **AND** the upload handler never runs and nothing is stored

#### Scenario: an image is stored under the type its bytes prove
- **GIVEN** a JPEG named `photo.png` that the browser declares as `image/png`
- **WHEN** it is uploaded
- **THEN** it is stored and answered as `image/jpeg`
- **AND** a file declared `image/png` whose bytes are not an image is stored as `application/octet-stream`

#### Scenario: an upload of a type no agent can use is refused
- **GIVEN** a binary file that is not an image, audio, a document or text, such as a video
- **WHEN** it is uploaded
- **THEN** the response is 415 `ATTACHMENT_TYPE_UNSUPPORTED`
- **AND** nothing is stored

### Requirement: Prune uploaded chat media on the retention cadence
The web composer's uploads MUST NOT accumulate without bound. On the retention
cadence, `~/.coffer/content/chat-media` MUST be swept by the same rule as the channel
media directory: a file whose mtime is more than 30 days old is deleted, with
no size cap and no reference check. A full prune reports the count under
`chat_media`, beside `channel_media`. A reference whose file is gone degrades
to a note that the file could not be read, and sending its id again is refused
as unknown.

#### Scenario: the chat-media prune deletes stale uploads and keeps fresh ones
- **GIVEN** `~/.coffer/content/chat-media` holding one upload older than 30 days and one recent one
- **WHEN** a full retention prune runs
- **THEN** the stale upload is deleted and the recent one is kept
- **AND** the prune result reports one deleted file under `chat_media`

### Requirement: Ship Claude Code and Codex subprocess providers on the type's one agent
System MUST ship subprocess-backed agent providers for Claude Code and Codex.
Each runs in a working directory (its `agent_config.cwd`); when a turn supplies
none, the provider MUST default to the Coffer-managed workspace
`~/.coffer/content/workspace` (created on first use) rather than reject the turn — so a
client with no configured workspace works out of the box. An
explicitly-supplied cwd MUST be an existing directory or the configuration is
rejected. Availability MUST reflect whether the agent's binary is resolvable on
the daemon's PATH; an unavailable agent is listed but not selectable.

A turn MUST stream the tool's line-delimited JSON output mapped onto the
platform's turn events, and persist the upstream session id so the next turn
continues the same session. Claude Code is driven through the Claude Agent SDK
and Codex through `codex app-server` (JSON-RPC 2.0 over stdio, NDJSON-framed);
both run with full permissions — owner pairing
([channels](../channels/spec.md)) is the security gate.

Both MUST emit the reply as text increments *as it is written*, not as one
block at the end of the turn, otherwise a live surface has nothing to grow and
a reply lands all at once after a long silence. The Claude Agent SDK does this
only when asked (`include_partial_messages`), and it then delivers BOTH the
increments and the finished assistant message, so the adapter MUST subtract
what it already emitted and send the reply exactly once.

A turn MUST run against the config directory of its type's one agent
([agent-registry](../agent-registry/spec.md) "Keep one agent per type, named by
it") while that agent is enabled — the same one whose models the pickers offer
([agent-registry](../agent-registry/spec.md) "Serve each agent type's model
catalogue from its one agent"); a disabled agent never answers. Coffer delivers skills, installs its
MCP entry and edits config files in that directory, so a turn that read any
other one would not see them. When that agent's `config_dir` is not its type's
standard location, the spawned process's environment MUST carry the variable the
product reads it from — `CLAUDE_CONFIG_DIR=<config_dir>` for Claude Code,
`CODEX_HOME=<config_dir>` for Codex — merged with the daemon's own environment
and with any key the provider projects; for the standard location (or when no
agent of the type is registered) the environment MUST be left as the daemon's
own, so the process behaves as when the user runs the CLI themselves.

#### Scenario: a streamed reply reaches the consumer exactly once
- **GIVEN** a Claude Code turn whose SDK delivers the reply as streamed increments and then as the finished assistant message
- **WHEN** the adapter maps the turn onto platform events
- **THEN** the reply arrives as one text delta per increment, in order
- **AND** the joined deltas equal the reply once, not doubled by the finished message
- **AND** the stream ends with a terminal turn-done

#### Scenario: a turn on an agent with its own config directory runs against that directory
- **GIVEN** a `claude_code` agent registered with a `config_dir` other than `~/.claude`, and a `codex` agent registered with a `config_dir` other than `~/.codex`
- **WHEN** a turn runs on each
- **THEN** the Claude Code process is started with `CLAUDE_CONFIG_DIR` set to the agent's `config_dir`, and the Codex app-server with `CODEX_HOME` set to its `config_dir`, the rest of the daemon's environment (and a projected provider key) intact
- **AND** a turn on an agent whose `config_dir` is its type's standard location starts its process with the environment untouched

#### Scenario: a disabled agent does not answer for its type
- **GIVEN** a `claude_code` agent registered with a `config_dir` other than `~/.claude`, then disabled
- **WHEN** a turn's environment is resolved for the `claude_code` type
- **THEN** it carries no `CLAUDE_CONFIG_DIR`, as when no agent of the type is registered
