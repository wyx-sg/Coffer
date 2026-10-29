# A Coffer Turn Takes Over a Session Open Elsewhere

**Status**: Accepted
**Date**: 2026-10-29
**Deciders**: Yuxing Wu
**Related**: [One Upstream Subprocess Set Per Downstream Client Session](session-subprocess-model.md), spec chat "Take over a session open elsewhere", spec channels "Route the owner's messages into a turn-platform conversation"

## Context

A Coffer conversation is an index row over the agent's own native session, and
a person can also open that session in a terminal (`claude --resume <id>`,
`codex resume <id>`). Two writers on one session would fork it, so until now a
turn was refused while the session was open elsewhere: before resuming, the
daemon looked for a process outside its own tree with the session id among its
arguments, and Codex's own refusal (JSON-RPC `-32600`, "already has an active
writer") was mapped to the same reply, "This session is open in a terminal —
continue there, or send /thread to start a new one."

On 2026-10-29 a SeaTalk conversation kept getting that reply long after the
person had closed the terminal. The holder was not a terminal. Recent Codex
CLIs attach to a shared, long-lived background app-server (`codex app-server
--managed-daemon`, under `~/.codex/packages/app-server-daemon`), and that
server holds the thread's writer lock (`~/.codex/thread-writer-locks/<id>.lock`).
Closing the terminal only disconnects a client. Codex's source says a loaded
thread is unloaded `thread_unload_delay_secs` (60 by default) after it has no
subscriber *and* nothing running. The lock was still held after more than 30
minutes, so the server still counted the thread as running; a turn left
waiting on an approval when the terminal closed never ends, because nobody can
approve it.

Two things were wrong. The reply blamed a terminal that no longer existed, and
a channel is used away from the computer, so "continue there" is advice the
person cannot follow. The person's direction: a closed terminal must not keep
the session, and even an open one should give way to the channel.

How comparable products handle a session open in two places:

- **Codex CLI** (the TUI) opens a thread another process writes read-only, or
  offers to fork it. It never takes the thread over.
- **Codex app and editor extensions** share one background app-server, so
  several windows can watch one thread; none takes write ownership from
  another.
- **Claude Code** has no lock and no background server. Two `--resume` of one
  session both append to it; avoiding that is left to the person. Because it
  has no background server, closing the terminal ends the process and frees the
  session at once.

All of them assume the person is at the computer and can close the other
window. Coffer's channel is used from a phone, which is why it has to act
where they do not.

## Options Considered

### Option A — The turn takes the session over (chosen)

Before a turn resumes a session, end every terminal process outside the
daemon's tree that names it (SIGTERM, SIGKILL after five seconds). When Codex
still answers "active writer", free the thread once and resume again: if
Codex's background app-server has the thread loaded, join it through that
server's control socket (`$CODEX_HOME/app-server-control/app-server-control.sock`,
JSON-RPC over a WebSocket), interrupt a turn left running there, unsubscribe,
and wait up to 90 seconds for the unload. If the lock holder is a terminal
`codex` with its own embedded app-server, found by the lock file among its open
files, end it. Leave every other holder (the Codex app's or an editor's own
`codex app-server`) alone and refuse with a reply that says so.

- **Pros.** The channel works from a phone without a trip to the computer. The
  stuck case fixes itself. The background server keeps serving everything else,
  so the Codex app and other threads are not disturbed. The same session
  continues; nothing is forked.
- **Cons.** Work running in the terminal on that session is interrupted. The
  background-server path waits for Codex's own unload delay (about a minute),
  during which the channel shows only that the turn is running. It speaks the
  background server's control protocol, which Codex marks experimental and may
  change; when it does, the takeover fails and the turn is refused with the
  accurate reply, which is no worse than before. A Codex thread opened by
  picking it inside a terminal that is still attached to the background server
  keeps it loaded, so that one case is still refused.

### Option B — Refuse by default with an accurate reply, take over on `/takeover`

Name the actual holder in the reply (a terminal, or Codex's background
server), and run Option A's takeover only when the person sends `/takeover`.

- **Pros.** Nothing running in a terminal is ever interrupted without being
  asked.
- **Cons.** Every stale lock costs a round trip and a command to learn. The
  common case, a terminal closed long ago, is exactly the one where there is
  nothing to protect, and it still needs the person.

### Option C — Stop Codex's whole background server

When it holds the thread, stop it (`codex app-server daemon stop` or a
signal).

- **Pros.** Simplest code: no control-socket client.
- **Cons.** It interrupts every other client of that server, including the
  Codex app and its running turns. On shutdown the server snapshots its loaded
  threads and restores them on its next start, so the thread can be held again
  as soon as anything starts the server.

### Option D — Run the turn inside the background server

Connect the turn itself to the background server and run it there, sharing the
loaded thread instead of freeing it.

- **Pros.** No waiting and no interruption.
- **Cons.** Joining a loaded thread ignores the resume overrides: Coffer's
  `developerInstructions` (the channel context), approval policy and sandbox
  would be the terminal's, so a turn could stop on an approval prompt nobody
  answers. The turn would also run with the background server's environment
  rather than the turn's own (`CODEX_HOME`, the turn token for turn-scoped
  tools).

## Decision

Option A. A Coffer turn takes over a session open elsewhere, ending terminals
that name it and freeing a Codex thread from Codex's background app-server or
from a terminal `codex`. Anything else that holds it is left alone, and the
turn is refused with "This session is open in another app that Coffer can't
close, such as the Codex app or an editor — close it there, or send /thread to
start a new one."

It is the only option that makes the channel usable from a phone in both the
stale and the open case, and the person asked for it. Option C trades a small
client for disturbing every other Codex window and does not even stick. Option
D loses the channel context and the turn's own environment. Option B keeps the
person in the loop for a case where there is nothing to protect.

## Consequences

- A turn on a session that a terminal has open ends that terminal's process,
  in the Coffer app's own conversations as well as in channels.
- A Codex turn whose thread the background server holds can take about a
  minute longer to answer, the server's unload delay.
- Coffer depends on the background server's control socket and on
  `thread/loaded/list`, `thread/resume`, `turn/interrupt` and
  `thread/unsubscribe`. If a Codex release changes them, the takeover fails
  safe into the refusal; the Codex adapter's tests cover the sequence.
- `websockets` becomes a direct dependency (it was already installed through
  `uvicorn[standard]`).
