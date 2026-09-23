## MODIFIED Requirements

### Requirement: Keep partial output when a turn is interrupted or fails
An interrupted or failed turn — user interrupt, adapter failure, timeout, or
daemon restart — MUST leave its partial assistant message persisted rather than
discarded: marked `complete` when the owner interrupted it, and `failed` when the
adapter failed, the turn timed out, or the daemon restarted under it. Stopping a turn is distinct from discarding the conversation, which
throws the turn away.

Two failures the platform detects itself, agent-agnostically: an agent whose
event stream ends without a terminal event (its process died or lost its
connection mid-turn) MUST be reported as a turn error (`stream_ended`), never
as a completed turn — a tick on a reply cut mid-sentence is a lie; and a turn
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

### Requirement: Open an archived conversation read-only
An archived conversation MUST open **read-only**: its history reads normally,
the composer and the model/effort controls are disabled, and a restore
control is offered in their place. Archived is a state the owner leaves
deliberately, not a thread that silently accepts a turn and unarchives itself.

#### Scenario: an archived conversation opens read-only
- **GIVEN** an archived conversation,
- **WHEN** it is opened on the Chat page,
- **THEN** its history reads normally, the composer and the model/effort
  controls are disabled, and a restore control is offered.

### Requirement: Let the owner set agent, model and reasoning level
The page MUST let the owner choose the agent a conversation runs on, on the
draft surface — once the conversation exists its agent is fixed and shown as a
label, because its upstream session and working directory belong to that one
agent (see "Record the agent on each conversation"). The page MUST let the owner
read and set the conversation's model and how hard that model thinks over
`GET|PATCH .../agent-config`, persisting both while
preserving the conversation's working directory and upstream session id, and
reverting to the agent's own default when either is cleared; a body that
mentions one leaves the other where it was.

The reasoning level is a SECOND control beside the model picker, not a variant
of it: the agents take it as their own field rather than as part of the model
name, and it renders only when the chosen model reports levels — nothing to
choose between means no control at all, not a disabled or empty one. Both
controls MUST be offered on the **draft** surface as well as in an open
conversation, because the first turn is the one a user most wants to pitch, and
by the time the conversation exists that turn is already running.

A missing Coffer LLM connection MUST NOT block the page: with none configured
the draft surface still accepts a message and the turn runs on the agent's own
built-in model and login, because a Coffer connection is an optional override,
not a prerequisite ([provider-switching](../provider-switching/spec.md), and the
2026-06-22 amendment of
[Provider Switching](../../../docs/decisions/provider-switching.md)).

#### Scenario: chat runs on the built-in model when no connection
- **GIVEN** a running daemon with no Coffer LLM connection configured for the
  agent,
- **WHEN** the Chat page is opened,
- **THEN** the draft surface is available with no blocking empty state, and a
  sent turn runs on the agent's own built-in model and login — a Coffer
  connection is an optional override, not a prerequisite.

### Requirement: Offer models from a fixed dropdown that keeps the current value
The model picker MUST be a fixed dropdown, never free text. Its options are the
models the platform offers for the agent
([provider-switching](../provider-switching/spec.md) "Serve one model list to
every surface": the agent's own catalogue, or the active connection's curated
ids when one is active) plus the **current value** — which MUST stay selectable
whatever that list contains, so a conversation never shows a picker that cannot
represent the model it is actually on. Nothing else is offered: the page does
not introspect a connection's endpoint itself.

#### Scenario: the model picker always offers the current value
- **GIVEN** a conversation set to a model the agent's catalogue does not list,
- **WHEN** the model picker is opened,
- **THEN** the current value is among the options and is selected, and the
  picker accepts no free text.

## ADDED Requirements

### Requirement: Search the conversation list by title
The Chat page's conversation list MUST offer a search box that filters the
listed conversations by title as the owner types: a conversation stays listed
when its title contains the query, compared case-insensitively with the query
trimmed, and clearing the query lists every conversation again. The filter runs
over the list already loaded for the current view (active or archived). A query
that matches nothing MUST show a no-match state that is distinct from the
empty-list state, and the search box MUST stay so the query can be changed; a
list with no conversations at all shows its empty state and offers no search.

#### Scenario: search narrows the conversation list by title
- **GIVEN** active conversations titled "Alpha rollout", "beta notes" and "Gamma"
- **WHEN** the owner types " ALP " into the list's search box
- **THEN** only "Alpha rollout" is listed
- **AND** clearing the search lists all three again

#### Scenario: a search that matches nothing is not an empty list
- **GIVEN** a conversation list holding one conversation
- **WHEN** the owner searches for text no title contains
- **THEN** no conversation is listed and the list says nothing matches
- **AND** it does not show the empty-list message, and the search box keeps the query

#### Scenario: an empty conversation list offers no search
- **GIVEN** a view with no conversations
- **WHEN** the conversation list renders
- **THEN** it shows the empty-list message and no search box
