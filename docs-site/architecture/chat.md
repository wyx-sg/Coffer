---
title: Chat and turns
description: How Coffer runs a turn on Claude Code or Codex, streams it to every surface watching, and lets IM channels drive the same conversations as the web Conversations page.
---

# Chat and turns

This page explains Coffer's turn platform: the conversation model, the orchestrator that runs one turn at a time per conversation, the adapters that drive Claude Code and Codex, the event bus that streams a turn to every surface watching it, and how IM channels plug in as a second client. It is written for engineers who want to understand the mechanism and the reasons behind it. For day-to-day use, see the [Chat guide](/guides/chat) and the [Channels guide](/guides/channels).

## The problem

The owner of a vault wants to talk to their coding agents from more than one place: a phone (through Telegram or SeaTalk) and a desktop browser. Both need the same guarantees. A turn has to reach an agent the same way whoever asked for it. A turn started on the phone has to be visible, interruptible and continuable from the browser. And no turn may end silently, including when the daemon dies halfway through a reply.

There is also a cost constraint. Coffer drives two agents and two IM platforms, and both sets are meant to grow. If each channel had to know about each agent, the integration cost would be N × M. The design keeps it at N + M.

## Design decisions

**One turn platform, several surfaces.** Conversations, the pending queue, the turn lifecycle and the event stream belong to one platform. The web Conversations page and every channel are clients of it. Once a message reaches the orchestrator, nothing downstream knows which surface it came from, and an agent cannot tell a phone turn from a browser turn.

**Single owner, one timeline, two screens.** Channels are owner-paired: the "IM peer" is always the vault's owner on their phone. So watching a phone conversation from the browser is continuity for one person, not multi-user collaboration. Coffer has no peer-identity model, no per-user visibility rules and no question of who may interrupt whom. The web page shows every conversation, including the ones a channel opened, with a badge naming the channel it is also reachable on.

**Starting a turn is separate from watching it.** `POST .../messages` starts or queues a turn and returns `202` immediately. All output flows through one subscription, `GET .../events`. The sender is not a special case: "the turn I started" and "the turn my phone started" travel the same path, and a replay buffer ensures the sender misses no early events.

**Send freely; queue, never reject.** A message sent while a turn is running joins a per-conversation FIFO pending queue. Each queued message becomes its own turn. Messages are not merged. The web composer never locks. A channel tells each waiting message its place ("⏳ Queued (n)") and accepts up to ten pending messages per conversation; the eleventh is dropped with the reason (see [the inbound pipeline](#the-inbound-pipeline)).

**The adapter is self-contained.** The orchestrator gives an adapter the conversation history and the turn's attachments, and nothing else. The adapter brings its own model, tools and configuration. Adding a third agent means registering one provider and one adapter. The conversation schema, the orchestrator and the clients do not change.

**Full permissions, owner pairing as the gate.** Both agents run without per-tool approval (`bypassPermissions` for Claude Code; `never` ask with `danger-full-access` for Codex). The trust boundary is the paired owner driving the conversation, not a tool-by-tool prompt that nobody is present to answer on a phone.

## Conversation model

A conversation is not a [resource](/architecture/resource-framework). It is a row in its own SQLite table of conversations, with its messages in a sibling table of chat messages. Chat state does not sync between machines.

| Field | Meaning |
| --- | --- |
| `id` | Opaque conversation id. |
| `agent_key` | The agent the conversation belongs to (`claude_code` or `codex`). There is no storage default: every writer names the agent explicitly. |
| `agent_config` | Provider-owned JSON: `cwd`, `session_id` (the upstream session to resume), and `model`. |
| `title` | Starts as a placeholder. It is replaced by the first user message's text unless the owner has already renamed the conversation. |
| `archived_at` | `null` while the conversation is active. |
| `channel_uid`, `peer_chat_id` | The optional channel binding: the return address for relaying output to an IM chat. It stores the channel's immutable uid, so it survives a rename. |

A message stores its `role`, an ordered list of content blocks (`text`, `tool_use`, `tool_result`, `attachment`), a `status` (`streaming`, `complete` or `failed`), and, for assistant messages, the `model_id` and token usage when the agent reports them.

The conversation's timeline is the record of what an agent did. Turns are deliberately **not** written to the [audit log](/architecture/observability). A turn is not irreversible, not security-sensitive and not invisible afterwards, so an audit row per turn would only duplicate the timeline.

### Working directory and session

Each turn runs in the conversation's `cwd`. If none was supplied, it runs in the Coffer-managed workspace `~/.coffer/content/workspace`, which is created on first use. An explicitly supplied `cwd` must be an existing directory, or conversation creation fails before anything is written.

The upstream session id is written back to `agent_config.session_id` after each turn, so the next turn resumes the same Claude Code session or Codex thread. Because the agent's own session already holds the conversation, the platform passes only the most recent **200** messages as history. That history is what a fresh session needs. A conversation with thousands of messages is never loaded in full.

If the agent no longer recognises a stored session id, the turn is retried **once** as a fresh session. Only a second failure becomes a turn error. Without this retry, a stale id would make the conversation permanently unusable instead of merely discontinuous.

### Which agent configuration a turn runs against

A turn runs against the config directory of the one registered agent of its type. This is the same agent whose models the pickers offer. When that directory is not the type's standard location, the spawned process gets `CLAUDE_CONFIG_DIR=<config_dir>` (Claude Code) or `CODEX_HOME=<config_dir>` (Codex), merged with the daemon's own environment. No provider key rides the environment: a [model provider](/guides/providers) connection that uses an API key is reached through Coffer's model proxy. For the standard location, the environment is left untouched, so the process behaves exactly as when you run the CLI yourself. This matters because Coffer delivers skills and installs its MCP entry into that directory. A turn that read a different directory would not see them.

## The turn orchestrator

The turn orchestrator is the one entry point for a message, from the web `POST` and from a channel alike. It knows the agent-provider registry and nothing about any specific agent.

Per-conversation state lives in one record: the event bus, the in-flight turn, the pending queue and a paused flag. The state is process-global and single-daemon by design. It exists only while something needs it (a turn in flight, a queued message or an attached subscriber) and is evicted otherwise, so a daemon that has served ten thousand conversations does not hold ten thousand buses.

### Sending a message {#enqueue-message}

1. Check that the conversation exists (404 otherwise).
2. If no turn is active, the queue is not paused and the queue is empty, start the turn now.
3. Otherwise append a pending entry (text, attachments, title hint and an optional start hook, which a channel uses to render the turn) to the queue and broadcast `queue_changed`.
4. Sending a message clears the paused flag, so a plain send after an interrupt resumes the held queue.

Starting a turn reserves the conversation's slot synchronously, before the orchestrator yields to anything else, so two concurrent sends cannot both start a turn. It then asks the registry for the conversation's provider, has it build an adapter, commits the user message (a text block plus references to its attachments) and spawns the detached turn task. When that task finishes, the orchestrator pops the head of the queue and starts its turn.

A queued turn that fails to **start** is neither lost nor retried in a loop. The message goes back to the head of the queue, the queue is paused, and a `turn_error` is published to the subscribers attached at that moment. The error belongs to no turn, so it is not kept in the replay buffer: a page opened or reconnected later sees the held queue, not a failure it cannot act on. For a channel message, the orchestrator also hands the channel's renderer a stream that carries the failure and then ends, because a phone has no queue chips to look at.

### Interrupt, delete and shutdown

The ways a turn can end early are told apart by marks on the in-flight turn, set by whoever cancels it:

| Cause | How it is signalled | Outcome |
| --- | --- | --- |
| Owner interrupt (`POST .../interrupt`, `/stop` in a channel) | The turn is marked interrupted; the queue is paused | `turn_done` with `stop_reason: "interrupted"`; the partial reply is kept as `complete`. |
| Conversation deleted | The turn is marked discarded | The placeholder row is deleted; the bus closes every subscriber. |
| Daemon shutdown | Neither mark | `turn_error` `daemon_stopped`; the partial reply is kept as `failed`. |

Stopping every turn is a step of the daemon's teardown and runs before the database closes. It closes the door first (no turn may start afterwards and every queue is paused, so a cancelled turn's end does not start the next one), cancels every running turn, and waits up to five seconds for their writes. A turn that does not settle in time is left to the startup sweep.

## The turn task

The turn task drives one adapter to completion. It is a detached background task, so it outlives the HTTP request or channel callback that started it. This is why a reply still completes and persists when the browser tab that sent it is closed.

```mermaid
sequenceDiagram
    participant UI as Web Conversations page
    participant API as Turn routes
    participant O as Turn orchestrator
    participant R as Turn task
    participant A as Agent adapter
    participant DB as Message store
    participant Bus as Conversation bus

    UI->>API: GET .../events (SSE)
    API->>Bus: subscribe (replay buffer + queue snapshot)
    UI->>API: POST .../messages
    API->>O: enqueue the message
    O->>DB: append user message
    O->>R: start detached task
    API-->>UI: 202 {queued: false}
    R->>DB: append assistant row, status streaming
    R->>A: run the turn (history, attachments)
    loop each event
        A-->>R: turn_start / text_delta / tool_call / tool_result
        R->>Bus: publish
        Bus-->>UI: SSE event
        R->>DB: flush partial (at most once per second)
    end
    A-->>R: turn_done
    R->>DB: finalise row, status complete
    R->>Bus: end the turn (drop replay buffer)
    R->>O: task finished, advance queue
```

What the task guarantees:

- **A placeholder row before the first event.** An assistant row with status `streaming` is written before the adapter produces anything and is finalised in place when the turn ends: one row, never a duplicate. When the daemon starts, a sweep flips every lingering `streaming` row (created before this daemon started, so a turn begun after it came up is never touched) to `failed`. No conversation reopens showing a reply that will never arrive.
- **Throttled partial saves.** The accumulated blocks are written onto the `streaming` row at most once per second. If an event is skipped by the throttle, a trailing write is scheduled for when the interval is up. So text streamed just before a long tool run is on disk within about a second. A daemon killed outright keeps what was streamed up to the last save.
- **An idle watchdog.** An agent can wedge without dying: a hung tool, or a CLI waiting on a prompt nobody will answer. If no event arrives for `COFFER_TURN_IDLE_TIMEOUT_SECONDS` (default `300`; `0` disables it), the wait is cancelled inside the adapter's event stream. This runs the adapter's own cancellation path, which interrupts and terminates the subprocess. The turn then ends with `turn_error` `turn_timeout`.
- **No silent completion.** If the adapter's stream ends without `turn_done` or `turn_error`, the task emits `turn_error` `stream_ended` itself. It does not rely on the adapter to do so, because a tick on a reply cut mid-sentence would be a lie.
- **Exactly one terminal event.** A cancellation that lands after a terminal event, for example during the final write, re-runs the finalise shielded from further cancellation and emits nothing more.

Three turn error codes belong to the platform rather than to an agent: `stream_ended`, `turn_timeout` and `daemon_stopped`.

### Turn and message states

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Running: message arrives, queue empty
    Idle --> Idle: message arrives while paused (queued)
    Running --> Running: message arrives (queued)
    Running --> Idle: turn_done or turn_error, queue empty
    Running --> Running: turn ends, next queued message starts
    Running --> Paused: interrupt
    Paused --> Running: any send or PUT pending
    Running --> [*]: conversation deleted
    Paused --> [*]: conversation deleted
```

The assistant row a turn writes has its own lifecycle: `streaming` → `complete` (normal end or owner interrupt), or `streaming` → `failed` (adapter error, `stream_ended`, `turn_timeout`, `daemon_stopped`, or the startup sweep after a crash).

## Events and the live mirror

A turn is a sequence of typed events. Each event's `type` is also its SSE event name on the wire, so clients dispatch on one vocabulary with no translation table:

| Event | Payload | Emitted by |
| --- | --- | --- |
| `turn_start` | none | adapter |
| `text_delta` | `text` | adapter |
| `tool_call` | `tool_use_id`, `tool_name`, `tool_input` | adapter |
| `tool_result` | `tool_use_id`, `tool_name`, `output`, `error` | adapter |
| `turn_done` | `prompt_tokens`, `completion_tokens`, `stop_reason` | adapter, or the turn task on interrupt |
| `turn_error` | `code`, `message` | adapter or turn task |
| `queue_changed` | `pending` (ordered texts) | orchestrator only |

The conversation bus fans each event out to every subscriber queue and keeps two things for late subscribers:

- a **replay buffer** of the current turn's events. It is cleared when a turn begins and dropped when the turn ends, because from then on the content is persisted and a late subscriber loads it from history. Replaying it as well would render the turn twice.
- the **latest** `queue_changed` snapshot only, not its history, because the queue is a conversation-level state and not turn content.

When a client subscribes, the buffer and snapshot are enqueued synchronously before its queue joins the subscriber set. Because a concurrent publish can only run on a later event-loop tick, no live event can arrive ahead of the replay.

The SSE route stays open across turns. With no turn running, it holds the connection open and delivers the next turn from whichever surface starts it. It ends when the conversation is deleted (the bus sends an end-of-stream marker) or the client disconnects. The web client re-subscribes whenever the stream drops, whether the connection closed cleanly or a read or fetch threw, and whether or not a turn was mid-flight, with linear backoff and a bounded number of attempts. After that it surfaces the error rather than hammering the endpoint.

### Routes

| Route | Purpose |
| --- | --- |
| `POST /api/v1/chat/conversations/{id}/messages` | Start or queue a turn. `202 {queued}`; carries no output. |
| `GET /api/v1/chat/conversations/{id}/events` | SSE subscription: replay the in-flight turn, then follow live. |
| `PUT /api/v1/chat/conversations/{id}/pending` | Replace the pending queue (reorder, drop, resume). Unpauses. |
| `POST /api/v1/chat/conversations/{id}/interrupt` | Stop the running turn and pause the queue. `204`. |
| `GET\|PATCH /api/v1/chat/conversations/{id}/agent-config` | Read or set the model; preserves `cwd` and the session id. |
| `GET /api/v1/agent-providers` | Registered agents with display name and availability. |
| `GET /api/v1/agent-providers/{agent_key}/models` | Models offered for an agent; 404 for an unknown key. |

Replacing the queue with `PUT .../pending` reconciles the new texts against the existing entries: each text reuses the first unused entry with the same text. A queue reordered from the browser therefore keeps each channel message's attachments and its channel renderer. Only a text that was not queued before becomes a new, bare entry.

::: info No CLI
Conversations are driven from the web page and from channels, over REST. The CLI has no chat commands, because it carries only what needs it ([chat spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/chat/spec.md)).
:::

## Agent adapters

The platform seam is two contracts:

- An **agent provider**, one per agent type. It validates and stores a new conversation's `agent_config`, builds a configured adapter for one turn, tears down agent state when a conversation is deleted, and reports availability: whether the agent's binary resolves on the user's `PATH` (the login shell's `PATH` merged with the daemon's inherited one) **and** an agent of that type is registered with Coffer. Chat talks to managed agents only, so an unavailable agent is listed but cannot be selected, and a turn for a type with no registered agent is refused (`AGENT_CONFIG_REJECTED`, reason `agent_not_managed`) rather than run against the CLI's default config directory.
- An **agent adapter**, one per turn. Given the history and the attachments, it produces an asynchronous stream of events. The adapter must end with a terminal event and must clean up and re-raise on cancellation. It may expose a `model_id`, which it learns while the turn streams (the Claude CLI names it on its assistant messages, the Codex app-server in its thread result). The turn task reads it when it finalises the reply and records it on the assistant message.

A registry holds the providers. They are registered at the composition root. No surface names a provider directly.

### Claude Code: the Claude Agent SDK

The Claude Code adapter drives Claude Code through the client in `claude-agent-sdk`, and it is the only part of Coffer that imports the SDK. Each turn resumes the stored session id, runs in the `bypassPermissions` permission mode, and asks for partial messages. Coffer's system context is appended to Claude Code's own preset prompt, not substituted for it.

Partial messages are what make a reply grow as it is written. With them enabled, the SDK delivers both the increments and the finished assistant message. The mapping to platform events subtracts what was already emitted, so the reply reaches consumers exactly once. On cancellation, the adapter interrupts and disconnects the SDK client and still persists the session id, which the SDK reports early, so an interrupted turn stays resumable.

### Codex: `codex app-server`

The Codex adapter drives Codex through `codex app-server`: JSON-RPC 2.0 over stdio, one JSON object per line (NDJSON, not LSP `Content-Length` framing). One read loop, using only the standard library, demultiplexes responses, server-to-client requests and notifications.

Each turn spawns an app-server process, resolving `codex` on `PATH`. The process is registered as a daemon child process, so the daemon's startup orphan sweep can clean it up after a crash. The adapter starts its notification pump **before** the handshake, so no notification emitted in response to the handshake is missed. It then runs:

1. `initialize`, then the `initialized` notification.
2. `thread/resume` with the stored thread id, or `thread/start`. Coffer's system context rides in `developerInstructions`, which adds to Codex's base instructions and does not replace them. A rejected resume falls back once to `thread/start`.
3. `turn/start` with the prompt. Coffer sends no `effort`, so Codex runs at the effort its own configuration names.

Notifications are mapped to platform events. On cancellation, the adapter sends `turn/interrupt`, persists the thread id and closes the process.

::: details Why a subprocess per turn rather than a pooled agent
Both adapters open a fresh session per turn and resume the agent's own stored session. The agent's state lives in the agent's own files, not in a long-lived process Coffer would have to supervise, health-check and recover after a daemon restart. The cost is process start-up per turn. The benefit is that a crashed or wedged agent affects exactly one turn, and a daemon restart loses nothing except the in-flight turn.
:::

### What the adapter is told

The appends an agent receives on top of its own system prompt are composed in one place, shared by both providers and always in this order:

1. For a channel-driven conversation, a note that the agent is on a chat channel. It names the platform, the chat kind and the channel, says what Markdown renders there, and asks for a reply shaped for a phone (outcome first, no step narration, long content under `## Details`, diagrams as PNG files, a `coffer__ask` call when the agent needs an answer). Chat does not import the channel kind for this: the channel kind publishes a reader that returns the note, built from the conversation's thread row and the rendering notes the running transport declares.
2. For a channel-driven conversation, the [memory](/architecture/memory) index. The composition root builds the memory composer and hands it to both providers, beside the per-prompt retriever that adds the notes a channel turn's message names to its prompt. It returns nothing when the index is empty, or when the tree cannot be read. See [Channel turns](/architecture/memory#channel-turns).
3. On every turn, a model note naming the model Coffer put the agent on, or saying the agent's own default is in use, with a few alternatives. An agent cannot see Coffer's choice and invents one when asked, so the note says it outranks the agent's own guess.

A turn from the web Conversations page, like a session you start yourself in a terminal, gets memory through the agent's own memory hook, when the agent is connected to Coffer. No turn gets it both ways.

## Attachments and document extraction

Attachments enter a conversation two ways. A channel downloads each file under `~/.coffer/content/channel-media` and hands the orchestrator an attachment (path, mime type, file name). The web composer uploads each file first, to `POST /api/v1/chat/attachments`, and sends the ids it gets back in `attachment_ids` on `POST …/messages`; the route resolves them to the same attachment values and calls the same orchestrator entry point, with the same attachments argument, that a channel calls. From there the two are one code path. Either way the chat database holds only a reference (an attachment block: `path`, `mime`, `filename`) inside the user message, never the bytes.

### Web uploads

A chat attachment service owns the upload's bounds and the send-time resolution; a file-backed media store holds the files.

- **Bounds.** One file per call, at most 20 MB (`ATTACHMENT_TOO_LARGE`, 413, naming the limit). The HTTP framework spools a multipart body to a temporary file while parsing it, so the upload route acts first: it checks the token, refuses a declared `Content-Length` over the limit plus a 64 KiB multipart allowance with the same 413 before reading the body, and parses the form accepting one file and a handful of fields. A body sent without a declared length is parsed and then refused by the same ceiling on the file's bytes. The type is decided by one rule: a declared image, audio or document type is kept, then a fixed extension table is consulted, and anything whose bytes are UTF-8 without a NUL is text. Anything else is `ATTACHMENT_TYPE_UNSUPPORTED` (415). An image's type is then replaced by what its magic bytes prove (PNG, JPEG, GIF, WEBP); one whose bytes are none of those is stored as `application/octet-stream`, never as an image. The table is fixed rather than the Python standard library's mime lookup, which reads the host's mime files.
- **Storage.** Each upload is two flat files under `~/.coffer/content/chat-media`: the bytes as `<id><ext>`, so a path-native agent still sees the extension, and `<id>.json` with the display name, type, size and stored file name, written after the bytes. The id is 32 random hex characters; the store joins nothing into a path that is not an id of that shape.
- **Send.** A message carries text, up to ten `attachment_ids`, or both. An id that names no stored file is `ATTACHMENT_NOT_FOUND` (422) and nothing is persisted or queued. A message with files and no text persists the stand-in text a channel's uncaptioned photo gets, because an agent request cannot hold an empty text block, and a conversation it opens is named after the files.
- **Resend.** The page's Retry calls `POST …/messages/{message_id}/resend`: the chat service finds the user row (`MESSAGE_NOT_FOUND`, 404, otherwise), the attachment service rebuilds its text and attachment values from the row's blocks, and the route enqueues them like a send, so a retry carries the original's files whether they came from the page or a channel. A referenced file the media sweep has deleted is `ATTACHMENT_EXPIRED` (410) and nothing is persisted or queued. Before the failed prompt's row has landed, the page instead re-sends its optimistic echo, which keeps the files' upload ids.
- **Retention.** `~/.coffer/content/chat-media` is pruned together with `channel-media` by the `attachments` retention policy: a file is deleted when its mtime is older than the policy's window (30 days by default; the user can change it or keep attachments forever under Settings → Data → Local content). The age rule is one kind-agnostic rule, the retention service runs one sweep per directory with the policy's window, and a prune reports the files removed from both under one key, `attachments`.

The page keeps each composer file's state (uploading, ready, failed), uploads through the shared API client, and holds **Send** while any file is uploading or failed. The optimistic echo of a sent message carries the files' names and types, so its chips show before the row lands, and an attachment-only echo is matched to its row by those names. There is no image preview: that would need a route serving the bytes back, and the path stays inside the daemon. The decision is recorded in [Chat Attachment Uploads](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/chat-attachment-uploads.md).

### Materialisation

The turn task does not receive attachments as a parameter. It reads them back from the last user message in the persisted history. That reference is the single source of truth, so it survives a daemon restart and matches what the page shows. The path never reaches the wire: only the adapter, which reads the bytes, sees it.

Each adapter then materialises attachments in its own shape, in this order:

1. **Audio** is transcribed and folded into the prompt, when a speech-to-text connection has been designated (see [internal engine](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/internal-engine/spec.md)). This is off by default. It is the one place user content may leave the machine for transcription. With no connection, or on any failure, the audio is handed over as an ordinary file.
2. **Documents** (PDF, Word, PowerPoint, Excel and similar) are converted to text by a document extractor, which lazily imports the optional `markitdown` library. If the library is missing or extraction fails, the document degrades to a file attachment.
3. **Everything else:** Claude Code receives an image inline, as a base64 image block, only when it passes the inline check: its bytes sniff as PNG, JPEG, GIF or WEBP, and it is at most 5 MB once base64-encoded (the Messages API's per-image ceiling). The block's media type is the sniffed type, not the stored one, so a mislabelled channel photo is not rejected as "image does not match media type". Any other file, including an image that fails either check, becomes a text note naming the saved path. The rule is applied at send time, so channel media and web uploads share it. Codex, which is path-native over the app-server protocol, always receives the path note, so it has no inline ceiling to respect.

## Channels as a second surface

A channel is a [resource](/architecture/resource-framework) of kind `channel`: a Telegram bot or SeaTalk app bound to the vault, with secret references, a default agent, an inverted agent scope (the agents this channel may drive), and `runs_on`, the machine whose daemon runs its adapter. The channel layer reaches the turn platform through exactly two seams, the chat service for conversations and the orchestrator's enqueue entry point for turns, in-process, just as the web page does over HTTP.

### Thin adapters over a shared core

A transport implements only the channel adapter contract: start and stop; outbound, send a text, open a live-text surface, edit a text and update a card; inbound, normalise platform events into four envelopes (a message, a button callback, a lifecycle event and a stop); and a record of its capabilities. Pairing, the owner gate, commands, queueing, conversation mapping and rendering strategy live in the shared core. The core chooses behaviour from capabilities, never from the adapter's type:

| Capability | Question the core asks |
| --- | --- |
| Live text | Is there a surface I can keep updating while the turn runs? |
| Edit | Can the transport rewrite a message it already delivered? |
| Buttons | Can it render interactive selection cards? |
| Card update | Can it rewrite an already-delivered card? |
| Typing | Can it show a typing indicator? |
| Message length | How long may one outbound message be? |

Both transports answer yes to live text by different means. Telegram edits one message. SeaTalk, which cannot edit a text message, uses its streaming API (`init_stream`/`update_stream`). A shared live-text surface holds the rules both share: never call the platform more often than the transport's buffer interval, remember the last snapshot, and stop using a surface after its first failure.

### Transports

- **Telegram** long-polls the Bot API directly over HTTP, with no bot SDK. The update offset is committed only after a dispatch attempt, so a crash re-delivers an update rather than losing it, and a dispatch that raises still advances past a poison update.
- **SeaTalk** receives over one outbound websocket connection per channel, held on a thread inside the daemon. The operator supplies the websocket SDK. It is synchronous, so its listen loop runs on a thread Coffer owns, and events are handed back to the daemon's event loop thread-safely. Coffer supervises reconnection itself: exponential backoff from 1 s capped at 30 s, and a flat 60 s after being kicked by another connection for the same app. Nothing is exposed to the network. Outbound calls use plain HTTPS.

Both transports drop redelivered events with a bounded in-memory set of recently seen ids (2048 entries).

### Supervision

The channel runtime is a reconciler that ticks every two seconds. On each tick it computes the wanted set by asking three gates in order: the channel is `enabled`, `runs_on` names this machine, and its scope leaves at least one agent to drive. It then starts, stops or restarts adapters to match. REST, CLI and UI never start or stop an adapter themselves, which keeps the reported status truthful; the one explicit request, `POST /channels/{uid}/restart`, asks the runtime to stop and rebuild a channel's adapter now, serialised with the tick. An adapter reads its secret once, when it is built, so the tick also compares a stamp of each secret the channel cites and rebuilds the adapter when a secret is replaced under the same ref. Runtime state is keyed by channel uid, so renaming a channel moves nothing that is running. The wanted-set computation is also the one place where the channel's agent uids become the turn platform's agent keys.

### The inbound pipeline

The inbound processor handles every inbound message the same way for every transport:

```mermaid
flowchart TD
    A["Transport receives event"] --> B{"Seen id before?"}
    B -- yes --> X["Drop"]
    B -- no --> C{"Group chat?"}
    C -- yes --> D{"Addressed to bot and sent by owner?"}
    D -- no --> X2["Drop, or refuse non-owner"]
    D -- yes --> F
    C -- no --> E{"Chat paired?"}
    E -- no --> P["Try pairing code"]
    E -- yes --> F["Fold quoted message and thread context"]
    F --> G{"Reserved command?"}
    H0 --> H["Command handler"]
    G -- yes --> H0["Release (or, for /stop, drop) the held burst first"]
    G -- no --> T{"One slip from a command?"}
    T -- yes --> TY["Answer: Did you mean …?"]
    T -- no --> I["Acknowledge, hold in the burst buffer"]
    I --> I2["Quiet window closes: one origin + every body"]
    I2 --> J["Turn driver submits"]
    J --> K["Orchestrator enqueues the message"]
    K --> L["On start: render events to IM"]
```

- **Owner gate and pairing.** A direct chat must match the paired peer. An unpaired chat can only present a pairing code: an 8-character single-use code, one-hour TTL, bounded wrong guesses, held in memory only. Strangers are ignored silently: no reply and no turn, so the bot never reveals it is alive. In a group, a message must be addressed to the bot and come from the owner's sender id. An unprovable sender is refused, never assumed to be the owner.
- **Conversation mapping.** Conversation identity is `(channel, chat, thread)`, stored in the channel's thread-to-conversation table. A direct chat and each group thread are independent conversations, so concurrent turns in different threads never contend. Each inbound entry resolves a conversation thread id apart from the reply thread id: a direct-chat thread keys to the direct chat's `""` conversation unless `/thread` opened it (its row carries a parallel-thread number) or the transport says direct-chat threads are deliberate rather than casual replies (as on Telegram). Keying uses the conversation thread id; sending uses the reply thread id, so a casual reply-in-thread keeps the direct chat's context and is still answered in its thread. On first use, the channel opens an ordinary conversation through the chat service with the thread's sticky settings (see [Commands and sticky settings](#commands-and-sticky-settings)); a sticky agent that has left the channel's scope gives way to the channel's default agent. If the conversation has been deleted, the next message creates a fresh one.
- **Commands** — the eight reserved words (see [Commands and sticky settings](#commands-and-sticky-settings)) — are handled by the command handler and never become turns. Control commands bypass the queue. Every other text, including one starting with `/`, is a message.
- **Bursts.** A burst buffer holds each `(channel, chat, thread)`'s messages until a quiet window passes (1.5 s after text, 5 s after a forwarded record or bare files) and releases them as one queued inbound: the last message's origin, every body in order, every attachment. The turn driver sends the receipt (a 👀 reaction, else typing) at arrival. A command awaits the release of its key first, and `/stop` drops what is held. Releases of one key are chained, so they reach the queue in order. Ordering before that is the transport's job: SeaTalk chains each chat's websocket ingests, and Telegram's poller already awaits updates one at a time.
- **Turns.** The message text is prefixed with its origin (platform, chat kind and title, thread, sender), so the agent knows where it is answering even after `/new <agent>` swaps the agent between conversations of one thread. When the conversation already has 10 messages pending, the turn driver drops the new one and says why (ten already wait), so a flood cannot pile up forever. Otherwise it enqueues the message with a start hook, and a message that was queued rather than started is answered "⏳ Queued (n)".

### Commands and sticky settings

The commands a phone can send are a small, closed vocabulary: `/new [agent]`, `/stop`, `/model [name] [level]`, `/dir [path|name]`, `/status`, `/resume [n]`, `/thread [title]` and `/help`. Only `/new`, `/stop` and `/help` work in a group, because they control the group's own conversation; the other five answer a group's owner with one private line pointing to a private chat. Keeping the set closed matters because every reserved word is a word the agent can no longer receive; everything outside it — an agent's own `/compact`, a skill's `/review`, a message that opens with a path — passes through as ordinary text.

- **One roster.** The commands live in one roster, and each entry carries its English and Chinese description, and whether it belongs in a group's menu and works there at all. The help text, every registered platform menu, the typo guard and the group rule are all rendered from it, so adding a command is one entry plus its handler and no list can fall behind. The typo guard answers a word within one or two edits of a command with "Did you mean …?" instead of running it or handing it to the agent, because a mistyped `/stop` that reached the agent as a message would be the worst possible outcome.
- **One grammar.** A bare command shows what is in effect (as a card where the transport has buttons), an argument sets it, and `default` resets it. Arguments are names a person reads — an agent's display name, a model's shown name, a directory's base name — never internal keys, and no answer prints an id.
- **Settings belong to the chat thread, not to the conversation.** The per-thread row that maps `(channel, chat, thread)` to its active conversation also holds that thread's chosen agent, model and working directory. A fresh conversation — `/new`, `/dir`, a deleted conversation replaced — opens with them, so clearing the context never throws away the owner's choices. In a group, the group's own row (thread id `""`) holds the group's defaults, which a group thread inherits for whatever it has not set, before falling back to the channel's default agent and configuration.
- **Structural versus parametric.** An agent session is tied to its agent and its directory, so `/new <agent>` and `/dir` open a fresh conversation; the model is re-read every turn, so `/model` applies to the next turn of the same conversation. A model chosen for one agent is cleared when the agent changes, because it names nothing the other agent runs.
- **An allow-list for `/dir`.** A channel's configuration lists the directories `/dir` may reach (each admitting the directories beneath it), beside the default directory new conversations start in (the default agent configuration's `cwd`); with none listed, `/dir` is off. The agent runs with full permissions, so which folders a phone can aim it at is decided at the computer, in advance, and never widened from chat.
- **Per-thread history.** Every conversation a thread opens is recorded against that thread. `/resume` reads only that history, so a chat can return to its own earlier conversations and never reach one from the web or from another chat, even with a forged button value.
- **Group main chat on SeaTalk.** A SeaTalk @mention in a group's main chat roots a new thread, so a setting sent there would configure a thread nobody continues. The transport marks such a message as the group's main chat, and a command there writes the group's defaults instead; `/stop` there interrupts every turn in the group.
- **Cards carry actions.** `/status` and `/help` are cards with Stop, New, Model, Resume and Dir buttons. A button carries the command's name, and a tap runs exactly what typing it runs, through the same owner gate as a message.

### Mirroring a web reply

A conversation a channel opened is one conversation with two screens, so a reply typed on the Conversations page must reach the phone too. Chat must not import the channel kind, so the dependency points the other way: **chat declares a mirror port** — "is this conversation mirrored, where to, and deliver this reply" — and **the channel kind implements it**, wired together at the composition root.

- **Where a reply may go.** The conversation is located through the per-thread history: its channel, chat, thread and chat kind. A direct chat, its threads and a group thread are deliverable. A group's main chat is not: it is the room's shared space, and a reply typed at a desk, followed by an answer nobody in the room asked for, does not belong there. Such a reply stays in Coffer. The conversation's view names the target (platform and thread mark) so the page can say where a reply will go before it is sent.
- **What is sent.** The reply is posted to that chat or thread under a first line `<your name> · from Coffer`, and the turn is queued with the same render hook a channel-driven turn gets, so the agent's answer reaches the chat exactly as it would have.
- **An outbox, never a drop.** When the channel is not running on this machine or the platform refuses the send, the reply is written to an outbox as pending, and the answer's final text is collected behind it. Nothing is discarded on failure. The channel reconciler's tick flushes a running channel's pending entries in order, backing off after a failure, and marks them delivered; until then the conversation lists them as not delivered. Only the send route mirrors, so a Retry on the page never posts a reply twice.

### Rendering

When the channel's message reaches the head of the queue, the orchestrator calls its start hook with a dedicated event queue for that turn. The channel's turn renderer drains it, and the work splits along four seams:

- **The status model** (pure). It tallies the turn — elapsed time, steps and failures, the latest narration — and draws the status block: `⏳ Working · 2m 14s · 7 steps`, a `💬` narration line, and the newest three step lines. In a direct chat each step line describes its call from its input (`✅ Read · wedding.json`); in a group it names only the tool, since input can carry a command or a query. The reply text is kept as the segments tool calls separate: the open segment is the answer tail, a closed one is narration, and the final reply joins them with paragraph breaks.
- **The live surface.** With live text, one surface grows for the whole turn. Each snapshot is the status block, a `─` rule, then the answer tail; the rule is the one contract with the transport, which clips the answer and never the block, and which may render the two apart (Telegram's rich draft puts the header in `<tg-thinking>`). The renderer redraws on a 10-second tick, the surfaces' own keep-alive cadence, so the clock moves during a silent tool. A surface that persists as the reply opens at once and carries the asker's @mention on every snapshot; scaffolding carries none.
- **The finish.** `MEDIA:` sentinels are uploaded; what the chat cannot show is rewritten, from capabilities: tables to bullets and a CSV where the chat does not render tables, code longer than the transport's inline limit to files; and a `## Details` section goes behind a summary card where the transport has cards but does not collapse details itself. A turn longer than the channel's `notify_after_seconds` whose answer finished a persisting surface sends one ping, because finishing a message created minutes ago notifies nobody.
- **The transport.** Adapters convert Markdown to their platform's format, chunk to the message length limit without cutting a fence, number continuations `(2/3)`, retry a rejected formatted message as plain text, and back off on rate limits. They declare the rest as capabilities: the reaction set (received, working, done, failed, stopped), the mention template (which may carry `{name}`), and the rendering notes for the agent.

A clean success sends no trailing summary, because the reply is the completion signal. A failed, interrupted or limit-hit turn sends one, and a long one's ping carries the same facts in its place.

The web page watches the same turn on the bus at the same time. This is how the live mirror works for channel conversations: the channel keeps only its renderer hook and never a buffer of its own, and a message queued from the browser behind a phone-started turn runs when that turn ends.

## Concurrency rules

- **One turn per conversation.** The slot is reserved synchronously when a turn begins. Every further message queues; a message is never refused because a turn is running.
- **Many conversations in parallel.** Turns on different conversations, including different threads of one group, run concurrently as independent tasks.
- **Single daemon.** Turn state, queues and buses are in-process. There is no cross-process fan-out, and the pending queue is lost on restart. That is consistent with an in-flight turn being marked failed on restart: an uncommitted message was never a row.
- **Ownership-checked release.** A finishing turn clears only its own in-flight record, so a start that raced it is never evicted.
- **Retention.** The framework's [retention worker](/architecture/observability#retention) archives conversations idle for 7 days (`conversations_archive`) and deletes archived conversations with their messages 30 days after archiving (`conversations`), unless the conversation has been written to within that window (an archived thread resumed from a phone is not deleted mid-use). Both windows are tunable like any other retained table.

## Trade-offs and alternatives

**One subscription versus a streaming POST.** A POST that streams its own turn, plus a subscription for everyone else, would be two event paths with races between them. The single subscription makes the sender an ordinary subscriber, at the cost of a replay buffer per active conversation.

**Sequential FIFO versus coalescing.** Merging all pending messages into one next turn would give the agent fuller context and use fewer turns. Coffer processes them one by one because the result is predictable, and each queued row maps to exactly one turn.

**An in-memory queue.** Persisting the queue would survive restarts, but restarts are rare, and dropping uncommitted messages matches how an in-flight turn is treated. The startup sweep makes the loss visible rather than silent.

**In-daemon channel adapters versus a separate gateway process.** A channel gateway process would isolate transports better, but would double the process-management surface (detect-or-spawn, PID files, logs) for a single-user daemon. Adapters run as supervised tasks, and SeaTalk's websocket runs as a thread, inside the daemon.

**Channels as MCP servers.** MCP is outbound, from agent to tool; a channel is inbound, from user to agent. Modelling channels as MCP servers would invert the data flow, so Coffer does not do it.

**No approval seat.** Both agents run with full permissions. An approval prompt sent to a phone would stall every turn on a person who is often not looking. Owner pairing is the gate.

## Where it lives in the code

| Package | Responsibility |
| --- | --- |
| `backend/coffer/domain/chat/` | Conversations, messages and their blocks, agent config, attachments, event types, errors |
| `backend/coffer/application/chat/` | The orchestrator, the turn task and its watchdog, per-conversation state, partial saves, the bus, the adapter contracts and registry, attachment handling |
| `backend/coffer/infrastructure/chat/` | Claude SDK and Codex app-server adapters, system-context composition, persistence, document extraction, transcription, the media store |
| `backend/coffer/surfaces/http/` | Conversation, turn (SSE), attachment and agent-provider routes, and the composition that wires repositories, registry, orchestrator, startup sweep and idle timeout |
| `backend/coffer/application/channel/` | Inbound pipeline, pairing, commands, turn driver, renderer, runtime reconciler |
| `backend/coffer/infrastructure/channel/` | Telegram and SeaTalk transports, live-text surfaces, Markdown rendering, media |
| `frontend/` | The Conversations page, its event subscription and bounded reconnect |

## Related

- Specs: [chat](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/chat/spec.md), [channels](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/spec.md), [channels/telegram](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/telegram/spec.md), [channels/seatalk](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/seatalk/spec.md)
- Decisions: [Chat Is a Single-Owner Live Mirror](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/chat-single-owner-live-mirror.md), [Channel Adapter Framework](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-adapter-framework.md), [Channel Attachments: Bytes on Disk, a Reference in the Message, Materialised per Agent at Send](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-attachments.md), [The Chat Page Uploads a File First and Sends Its Id, Into a Sibling Media Directory](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/chat-attachment-uploads.md), [SeaTalk Inbound Over WebSocket](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/seatalk-websocket-inbound.md), [Coffer's Own Model Is an Internal Engine, Not a Persona or a Tool](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/coffer-model-is-an-internal-engine.md), [Managed Agents Run With Full Permissions; Owner Pairing Is the Gate](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/managed-agents-run-with-full-permissions.md)
- Pages: [Daemon and processes](/architecture/daemon), [Persistence](/architecture/persistence), [Memory](/architecture/memory), [Security model](/architecture/security), [Chat guide](/guides/chat), [Channels guide](/guides/channels)
