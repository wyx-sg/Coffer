# Telegram Inbound Is a Long Poll That Commits the Offset After Dispatch

**Status**: Accepted
**Date**: 2026-06-12
**Deciders**: Yuxing Wu
**Related**: spec channels/telegram ("Receive updates by long polling", "Subscribe to the bot's own membership changes"); spec channels ("Process each inbound event once"); [Channels Are Machine-Local Resources, Like Agents](channels-are-machine-local-resources.md);
[Channels Are Thin Transport Adapters](channel-adapter-framework.md), [SeaTalk Inbound Over WebSocket](seatalk-websocket-inbound.md);
PRs #59, #356

## Context

The Telegram Bot API delivers updates to a bot one of two ways: a **webhook**
(Telegram POSTs each update to an HTTPS URL the bot registers) or
**`getUpdates`** (the bot asks, and the call can be held open as a long poll).
Each update carries an increasing `update_id`; passing `offset = last + 1`
confirms everything before it, and Telegram then stops re-delivering it.

Coffer's daemon binds to loopback and nothing else may listen
([principles](../../docs-site/architecture/principles.md), "Network
defaults"). It is always up once started, so a poll it makes is always there
to receive. The failures that matter are a daemon crash between receiving an
update and handling it (the update must not be lost) and one update that
crashes the handler every time (it must not wedge the channel).

## Options Considered

### Option A — Long polling; commit the offset only after the dispatch attempt (chosen)

`poll_updates` (`infrastructure/channel/telegram_poll.py`) calls `getUpdates`
with a 50 s timeout and the update types Coffer subscribes to, dispatches each
update to the core, and only then advances the offset past it. A dispatch that
raises is logged and the offset still advances, so a poison update is skipped
rather than retried forever. A failed poll backs off on a 1 s → 5 s → 30 s
ladder, the last step repeating. A crash before the offset advances means the
update is re-delivered; the adapter's recently-seen id set drops the duplicate
if it had already been handled.

Pros: no public endpoint, no TLS certificate, no tunnel; works behind any NAT
or laptop network; the daemon owns delivery pacing. At-least-once delivery
with de-duplication gives effectively-once handling.

Cons: one open HTTPS request per channel at all times; a reply to an update
arrives up to one poll round-trip later than a webhook would push it (in
practice sub-second, since a long poll returns as soon as an update exists).
Only one consumer may poll a bot, so a second machine running the same bot
competes for its updates (Telegram answers the second poller with
409 Conflict) — a channel is never synced, so a second machine polls the bot
only if the person creates the channel there too.

Wins because it satisfies loopback-only with nothing to operate.

### Option B — Webhook

How it works: register an HTTPS URL with `setWebhook`; Telegram POSTs updates
to it.

Pros: push delivery; no idle open connection.

Cons: needs a publicly reachable HTTPS endpoint with a valid certificate, so a
tunnel or a hosted relay, a listener process and secret-token verification —
the same apparatus Coffer deleted from SeaTalk ([SeaTalk Inbound Over
WebSocket](seatalk-websocket-inbound.md)) — for no gain a local daemon needs.

Loses because it requires a public address the vault does not have.

### Option C — Long polling, committing the offset before dispatch

How it works: advance the offset as soon as a batch arrives, then handle it.

Pros: an update is never delivered twice.

Cons: a crash between commit and dispatch loses the owner's message silently.

Loses because a lost message is worse than a duplicate that de-duplication
already absorbs.

## Decision

Telegram inbound is a `getUpdates` long poll per channel, run inside the daemon
by the channel's adapter. The offset advances only after each update's dispatch
has been attempted — succeeded or raised — and a failing poll backs off
1 s, 5 s, then 30 s repeatedly. Duplicates from re-delivery are dropped by the
adapter's seen-id set.

## Consequences

- No Telegram code path listens on a socket.
- A crash re-delivers at most the updates of the batch in flight.
- A bot token must be polled by one daemon only; a channel is a machine-local
  resource, so it is never started by a machine the person did not create it
  on ([Channels Are Machine-Local Resources, Like Agents](channels-are-machine-local-resources.md)).
- Enforced by: `infrastructure/channel/telegram_poll.py`,
  `domain/channel/dedup.py`.
