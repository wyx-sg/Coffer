---
title: The event stream
description: How a page learns that something changed — one daemon-wide stream of invalidation hints, resumable across a dropped connection, with a resync when too much was missed.
---

# The event stream

The web UI shows state that changes behind its back: an agent edits a server's file, a reconcile pass repairs an agent's config, a sync round imports a skill from another machine, an MCP server starts failing. The page has to find out. This page explains the mechanism Coffer uses for that: one stream for the whole daemon that says *what* changed, never *how*. The decision and the options weighed are in the ADR [The Wire Contract Is Generated From the Pydantic Models](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/wire-contract-generated-from-the-pydantic-models.md) (the event-stream section).

## Hints, not state

Each event on the stream is a small envelope: a sequence number, the kind of thing that changed, which one, the revision it is now at, and whether it was written or deleted. That is all. It carries none of the thing's fields.

A client that receives one invalidates whatever it has cached for that thing and fetches it again through the ordinary API. This is deliberate. If the stream carried the new state, it would be a second description of every resource, with its own shapes, its own redaction rules and its own ordering guarantees, and it would have to agree with the REST API forever. As a list of hints it cannot disagree with anything: the REST API stays the only place state is read from, and the stream only says when to read it again.

The same property makes lost events harmless in the worst case. A client that misses a hint shows stale data until its next refetch; it never shows wrong data that the stream invented.

## Where the hints come from

Every write to a resource — whether it came from the web UI, an agent's MCP call or a sync import — passes through the resource framework, which already announces it to the [reconciler](/architecture/reconciler) so the next pass can come sooner. The event stream listens at the same place. No kind has to remember to announce its own writes, so no kind can forget to.

The one thing that is not a resource write is the "needs you" list on the Overview page. It is computed on demand from each kind's own signals — a server whose test failed, an agent that is not connected, a sync stopped on a conflict — and nothing records the moment it changes. So the daemon watches it: after resource writes, after each reconcile pass and on a slow timer it recomputes a fingerprint of the list, and announces an `attention` change only when the fingerprint moves. The fingerprint covers which items there are and how severe, not their wording, so rewording a message does not wake every page.

The list is computed once for every reader. The daemon keeps the watcher's last answer and hands it to the Overview, the sidebar and the menu bar for up to the watcher's period. It drops that answer the moment something may have changed the list: a resource write or reconcile pass (the watcher's own nudge), an ignore, or any request other than a read, which covers actions that are not resource writes, such as approving a secret request. A read after an action therefore never sees the list from before it. The desktop window's menu-bar count follows the change feed rather than polling; only while the window is closed does the shell read the list itself.

## Numbering, replay and resync

Every envelope gets the next number in a sequence that starts at 1 each time the daemon starts. The daemon keeps the most recent envelopes — about a thousand — in memory.

Connections drop: a laptop sleeps, the desktop app reloads, the daemon restarts. A client that reconnects says which event it saw last, the way any Server-Sent Events client does, and the daemon replays everything after it that it still holds before going live. Nothing is lost across a short gap. Because the numbering starts again at every start, an event's id names the daemon run as well as the number, so "event 5" from before a restart is never mistaken for this run's event 5.

When the gap is too long — the number is older than anything the daemon still holds, or it names an event this run never issued because the daemon restarted in between — replay cannot be complete. Rather than replay part of it and let the client believe it is up to date, the daemon sends one `resync` event first. It means "you may have missed something": the client refetches everything it shows, and then follows the live stream as normal.

The same rule protects the daemon from a slow reader. Each connection may hold only a bounded number of undelivered events. A client that falls further behind loses its backlog and receives a single `resync` instead, so one stalled tab cannot make the daemon's memory grow.

## Keeping the connection honest

While nothing changes, the stream sends a `heartbeat` event at a fixed interval, carrying the latest sequence number. A client that stops receiving heartbeats knows the connection is dead rather than merely quiet, and reconnects. A heartbeat also tells a client that has just reconnected whether it is behind.

## Reading it from a page

The stream is gated by the same token as every other management call. A browser's built-in `EventSource` cannot send a custom header, so the page reads the stream with `fetch` and parses the events itself — the same way it already reads a chat conversation's live output. The chat stream stays separate: it carries the content of a turn, which is state, not a hint.

A page that shows live state follows the stream while it is open: Overview does, so a "needs you" row disappears as soon as its problem is resolved, and Activity does. The reader lives in one place in the web UI and keeps itself connected: when a connection ends it waits a moment and reconnects with the id of the last change it saw, and it waits longer after each refused attempt, so a daemon that is down costs a request every few seconds rather than a tight loop. On each `change` it invalidates the cached lists that kind is read through; on `resync` it invalidates everything; the page's own queries then refetch through the typed endpoints.

Two lists the web UI shows are not on the stream, because neither is a resource: the audit log and the MCP call log. Activity therefore re-reads the newest page of each every few seconds — a few rows, not the whole list — and also re-reads the audit log's newest page whenever a `change` arrives, since a resource write leaves an audit entry behind.

## What pages can stop doing

Before this stream, each page kept itself fresh by polling on its own timer, between five seconds and a minute, so a change could take up to a minute to appear and a page that shows every kind would have had to poll every kind. With one stream, a change appears as soon as it is written, and a page refetches only what an event names.

## Growing lists page by cursor

The lists a page fetches after a hint have the same problem in a different form: the audit log, the MCP call log, the Conversations list and an agent's sessions all grow while someone is paging through them. Paging by position ("skip the first 50") shifts every later page when a new row arrives at the top, so rows repeat or vanish between pages. These lists page by an opaque cursor instead: each answer names where the next page starts, as a position in the list's order rather than a count, and that position does not move when rows are added in front of it. A cursor is tied to the list and the filters it was issued for; sending it anywhere else is refused rather than guessed at.
