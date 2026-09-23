## MODIFIED Requirements

### Requirement: Keep partial output when a turn is interrupted or fails
An interrupted or failed turn — user interrupt, adapter failure, a stream that
ends without a terminal event, timeout, daemon shutdown, or a daemon that dies
outright — MUST leave its partial assistant message persisted rather than
discarded: marked `complete` when the owner interrupted it, and `failed` in every
other case. Only deleting the conversation discards a turn: the running turn is
cancelled and its placeholder row removed with the conversation. Stopping a turn
is distinct from discarding the conversation.

The partial text MUST be saved onto the turn's `streaming` row while the turn
streams, at most once per second — never per token — so a daemon that dies
outright keeps what was streamed up to the last save, which the startup sweep of
"Sweep streaming rows left by a crashed daemon" then marks `failed`. A save that
lands after the row was finalised MUST NOT change it.

A daemon shutdown MUST stop running turns itself, before the database closes:
each is cancelled, emits a `daemon_stopped` turn error, and keeps its partial
reply marked `failed`, the shutdown waiting a bounded time for those writes; a
turn that does not settle in that time is left to the startup sweep.

Three turn errors are the platform's own rather than an agent's —
`stream_ended`, `turn_timeout` and `daemon_stopped`. Two of them it detects
agent-agnostically: an agent whose event stream ends without a terminal event
(its process died or lost its connection mid-turn) MUST be reported as a turn
error (`stream_ended`) by the platform's turn runner whether or not the adapter
reports it, never as a completed turn — a tick on a reply cut mid-sentence is a
lie; and a turn
that produces no event for the idle window
(`COFFER_TURN_IDLE_TIMEOUT_SECONDS`, default 300; `0` disables the watchdog)
MUST be cancelled with a `turn_timeout` error, its agent process stopped
through the adapter's own cancellation path. In both cases whatever text
streamed before the failure is kept on the assistant message (marked failed)
and delivered ahead of the notice.

#### Scenario: stop a running turn
- **GIVEN** a turn that has streamed partial text and is still running,
- **WHEN** it is interrupted,
- **THEN** the stream ends with a terminal turn-done carrying stop reason
  `interrupted`, and the partial assistant message is persisted as complete.

#### Scenario: a silent turn is cancelled by the idle watchdog
- **GIVEN** an agent that streams part of a reply and then produces nothing,
- **WHEN** the idle window passes,
- **THEN** the turn ends with a `turn_timeout` error, the agent's cancellation
  path runs, and the partial reply is kept on a message marked failed

#### Scenario: an errored turn still delivers what it streamed
- **GIVEN** a turn that streamed text before failing,
- **WHEN** the channel renders it,
- **THEN** the chat receives the text, then the error notice, then the failed
  summary

#### Scenario: a stream that ends without a terminal is a failure, not a reply
- **GIVEN** an agent that streams part of a reply and then ends its event stream with no terminal event,
- **WHEN** the turn is driven,
- **THEN** the last event every subscriber receives is a `stream_ended` turn error and no turn-done is emitted
- **AND** the assistant message keeps the streamed text and is marked failed

#### Scenario: a daemon that dies mid-turn keeps what was streamed
- **GIVEN** a turn that has streamed text for longer than the save interval and is still running,
- **WHEN** the daemon dies without finalising the turn and a new daemon starts on the same database,
- **THEN** the startup sweep finds the assistant row, marks it failed, and the row carries the text streamed up to the last save
- **AND** a turn streaming hundreds of tokens saves at most once per second, not once per token

#### Scenario: a shutdown keeps the partial reply
- **GIVEN** running turns that have streamed partial text,
- **WHEN** the daemon shuts down,
- **THEN** the turns are stopped before the database is closed, each ending with a `daemon_stopped` turn error
- **AND** each assistant message keeps its streamed text, marked failed


### Requirement: Show every conversation on the Chat page
The web UI MUST carry a **Chat page**: two columns, the conversation list on
the left and the selected conversation's message thread with its draft surface
on the right. The list MUST show every conversation in the vault not owned by
another surface, whatever opened it — a conversation carrying an `owner` belongs
to that surface, is left out of the list, and stays readable by id — so a
conversation an IM channel created is listed, readable,
watchable, and continuable from the page, and carries a badge naming the
channel it is also reachable on. There is no web-only conversation kind: the
page and the channel are two windows onto one timeline, driven by one owner,
and an agent cannot tell which window a turn arrived through.

#### Scenario: a channel's conversation is listed beside the web's with a badge
- **GIVEN** one conversation started on the web page and one opened by an IM channel
- **WHEN** the Chat page's conversation list renders
- **THEN** both conversations are listed
- **AND** only the channel's conversation carries a badge naming its channel
