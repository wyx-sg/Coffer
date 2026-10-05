## Context

Two listings exist today. `GET /api/v1/chat/conversations` reads the conversation
index in `runs.db`, which holds one row per channel thread and nothing else
([chat data model](../../specs/chat/data-model.md)). `GET /api/v1/agents/{uid}/sessions`
asks one agent for its native sessions — Claude Code through the Agent SDK, Codex
through a short-lived `codex app-server` — and joins the conversation index so a
session a channel conversation points at carries `conversation_id`, `running`,
`needs_you` and its channel binding. The second already covers the first: a channel
conversation becomes a native session as soon as a turn runs on it. Both lists are
drawn by the same `SessionRow`.

## Goals / Non-Goals

**Goals:** one list of every session of every managed agent, newest activity first,
filterable by where it started and by agent; starting a new session from it.

**Non-Goals:** showing session text; starting a session anywhere but a terminal.

## Decisions

### Merge the agents' listings in the daemon, not in the browser

`GET /api/v1/agent-sessions` calls each managed agent's `NativeSessionService.list`
concurrently and merges by `(last_activity_at desc, agent key, session_id)`. The
browser could fan out and merge, but then paging, filtering and the partial-failure
rule would live in two places and the cursor would be the client's. Rejected.

**Cursor.** An agent's own cursor only points after a page it returned, so the
merged cursor records, per agent, the agent cursor of the page its next unconsumed
row sits on and how many rows of that page were already consumed:
`{agent: {c: <agent cursor or null>, skip: n, done: bool}}`, plus the filters it
was issued for, base64-encoded and opaque ([resource-framework](../../specs/resource-framework/spec.md)
"Page growing lists by an opaque cursor"). Each page re-reads, per agent, at most
one page of `limit` rows from `c`, drops `skip`, merges, emits `limit`, and writes
the new positions. A session whose activity moves while someone pages may be seen
twice or skipped, the same as the per-agent listing; the next refresh settles it.

**Total.** There is none: Codex cannot count without reading everything, so the
answer carries `next_cursor` only and the page shows no count (it already shows
none).

### Source filter

`source` is a comma-separated set of `local` and channel uids.

- Only channel uids: the rows are exactly the index rows of those channels, so the
  listing pages the index (the query the removed route used) and asks each row's
  agent for nothing — its title, cwd and times are the index's. This keeps a
  channel conversation with no native session yet (no turn has run) visible under
  its channel, disabled to open, as today.
- `local` (with or without channels) or no source: the merged agent listing, where
  `local` keeps sessions no conversation points at, and channel uids keep those
  whose conversation is that channel's. Filtering after the merge can leave a page
  short; the service reads further pages per agent until it has `limit` rows or
  every agent is exhausted, bounded at five agent pages per agent per request, after
  which it returns what it has with a cursor.

`agent` narrows which agents are asked. `q` is passed to each agent's own search:
Claude Code matches title and working directory, Codex its server's title filter —
the per-agent behaviour of "List an agent's native sessions through the agent".

### Partial failure

An agent whose listing raises is left out of the page, and the answer carries
`unavailable: [{agent, reason}]`. Its cursor position is kept, so Retry (re-reading
the first page) or the next page picks it up when it answers again. The page shows
one line above the list — "Couldn't read Codex's sessions · Retry" — instead of an
error state, which is kept for when every agent fails.

### Row actions route by what the row is

Rename, Delete and Stop act through the routes that exist: a row with a native
session renames and deletes through `/agents/{uid}/sessions/{session_id}` (which
already retitles or removes its conversation); a channel row with no session yet
through `/chat/conversations/{id}`; Stop is the conversation's interrupt. Nothing new
on the wire.

### New conversation

The terminal route's body becomes "at most one of `resume` and `prompt`"; neither
runs `cd '<cwd>' && claude` (`codex`). The dialog is a dialog, not a page, because it
is two fields ([web-ui](../../specs/web-ui/spec.md) dialog-versus-page convention). Its
default directory is Coffer's workspace `~/.coffer/content/workspace`, the
directory a channel conversation starts in by default, and the agent is the one last
chosen (kept in `localStorage`), falling back to the first managed agent. The new
session is not inserted into the list optimistically — Coffer does not know its id —
and appears on the next refresh, which the window regaining focus from the terminal
triggers.

### Removing `GET /api/v1/chat/conversations`

The list has no other caller once the page reads the merged listing; the 1.0 rule is
to leave no unused route ([no backward compatibility](../../../docs-site/architecture/principles.md)).
`Narrowing` and the count query move into the channel-only branch of the new
listing rather than being deleted.

## Risks / Trade-offs

- **Latency** — every page asks every agent; Codex spawns an app-server per call.
  Mitigation: agents are asked concurrently, and the per-agent listing already
  bounds its own work. If it proves slow, a short-lived per-agent page cache keyed on
  the agent cursor is the follow-up.
- **Scenario names** — every existing scenario keeps its name, so their acceptance
  markers stay; "the Channel pill filters by several channels" now drives the Source pill.
