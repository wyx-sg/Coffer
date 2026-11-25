# The Short Version of a Long Channel Reply Gets 20 Lines, and the Bound Is 25

**Status**: Accepted
**Date**: 2026-11-25
**Deciders**: Yuxing Wu
**Related**: [A Long Channel Reply Is Rewritten Short by the Agent](long-channel-reply-is-rewritten-short.md) (this amends its line budget), [A Channel Reply Is Plain Text, With No Card or Button](a-channel-reply-is-plain-text.md), spec channels "Ask for the short version of a reply too long for a chat"

## Context

The short version asked for after a too-long reply said "in at most 5 lines".
The owner hit this on 2026-11-25: a 56-line summary of a problem came back as
five lines, coarse and with its structure gone, because five lines cannot hold a
conclusion plus the facts behind it. The bound that triggers the rewrite (20 lines
or 1,500 characters) and the length the rewrite is asked to meet were set
separately, so the rewrite was asked for far less than the chat can read.

Constraints that stay: Coffer keeps no reply text, so it cannot store a long
reply; a reply that reaches the chat must read as a whole message; and the full
report stays a file on request.

How comparable products handle a long answer in a chat (public docs and product
behaviour as of 2026-11; search results were thin, so the points below are
summarised from what was found and marked where inferred):

- **Claude in Slack**: long work goes to a canvas or file, with a short message
  pointing at it (inferred from the product; not stated in the docs found).
- **Devin in Slack**: a short result; detail in its worklog, linked.
- **OpenClaw**: an oversized reply is split into ordinary chunks and delivered in
  parts, with a per-channel size.
- **Telegram Bot API**: a single text message is at most 4,096 characters; longer
  text has to be split by the sender. A bot that wants structure has to fit it in
  that size or send several messages.

None of them cuts a summary down to a skeleton; the ones that keep a chat readable
either keep the answer whole and short enough to read, or move the rest behind a
link or file.

## Options Considered

### Option A — Keep 5 lines (status quo)

- Pros: nothing to change; the shortest possible chat messages.
- Cons: the problem in the 2026-11-25 screenshot. A 5-line limit cannot carry a
  conclusion, its evidence and a next step, so every summary loses structure.

### Option B — Raise the rewrite target to 20 lines and 1,500 characters, keep the 25-line bound (chosen)

The short version is asked to fit 20 lines and 1,500 characters, with a few
headings or a short list allowed. A reply past 25 lines or 1,500 characters is
still rewritten, so the rewrite always lands inside the bound it was triggered by.

- Pros: a 20-line budget carries a conclusion, a few grouped facts and the next
  step with its structure; the rewrite stays a whole message; the full report is
  still a file on request; one small change in the prompt and two constants.
- Cons: a 20–25 line chat message is still long on a phone; a dense Chinese
  paragraph near 1,500 characters reads as a wall. The bound is a constant, so
  any future change is a code change, not a setting.

### Option C — Raise only the bound, keep the rewrite target at the old size

- Pros: fewer replies rewritten.
- Cons: the rewrite target stays at 5 lines, so every reply past the bound is
  still cut to 5 lines. This does not fix the reported problem.

### Option D — Bound by characters only, drop the line count

Allow about 3,000 characters per message and split longer text across messages.

- Pros: the line count stops mattering; a short list of many short lines is not
  penalised.
- Cons: Telegram's limit is 4,096 characters, so a split would be needed above
  it, and a split reply reads as several messages where the owner wanted one.
  SeaTalk's limit was not checked, so it could not be settled here. The split
  also brings back "half a message" for the replies that run past the first part.

### Option E — Per-channel limits as settings

Each channel gets its own line and character budget, editable by the owner.

- Pros: fits each platform's real limit.
- Cons: a setting for a number nobody has asked to tune. Coffer's rule is that it
  does not add settings the agent or a fixed default can settle; one bound for all
  chats is enough until a platform shows it cannot take it.

## Decision

Option B. The bound stays 25 lines and 1,500 characters
(`application/channel/reply_rewrite.py`, `MAX_REPLY_LINES`, `MAX_REPLY_CHARS`), and
the short version is asked for at most `REWRITE_MAX_LINES` = 20 lines and 1,500
characters, keeping a few headings or a short list where they help. The rewrite
still ends with one line offering the full report as a file. It is a constant,
not a setting, as in the ADR it amends.

## Consequences

- A summary that needs structure now keeps it, within 20 lines.
- Replies between 21 and 25 lines and under 1,500 characters are sent as written.
- The per-platform size question (Telegram 4,096, SeaTalk unverified) is not
  settled here; Option D would need it settled first.
