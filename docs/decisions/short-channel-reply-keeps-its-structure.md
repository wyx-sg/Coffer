# The Short Version of a Long Channel Reply Keeps Its Structure in 12 Lines

**Status**: Accepted
**Date**: 2026-11-25
**Deciders**: Yuxing Wu
**Related**: [A Long Channel Reply Is Rewritten Short by the Agent](long-channel-reply-is-rewritten-short.md) (this amends its line budget), [A Channel Reply Goes Out as the Agent Wrote It](a-channel-reply-goes-out-as-the-agent-wrote-it.md), [A Channel Reply Is Plain Text, With No Card or Button](a-channel-reply-is-plain-text.md), spec channels "Ask for the short version of a reply too long for a chat"

## Context

A reply past 20 lines or 1,500 characters is not sent; the agent is asked, in the
same conversation, for a short version. That request said "only the conclusion
and what the reader needs to act on, in at most 5 lines". On 2026-11-25 the owner
got a 56-line problem summary back as five dense lines: coarse, and with every
group and list of the original gone. The owner's words: shortening is fine, but
the result must still be clearly structured, or the chat cannot be understood.

Two things went wrong: five lines leave no room for more than a conclusion, and
the request said nothing about shape, so the agent squeezed the answer into a few
run-on sentences.

Constraints that stay: Coffer keeps no reply text; what reaches the chat is a
whole message; the full report is a file, sent when the owner asks.

How comparable products handle a long answer in a chat (public docs and product
behaviour as of 2026-11; the search found little written down, so this is a
summary, with inferences marked):

- **Claude in Slack**: long work goes to a canvas or file, with a short message
  pointing at it (inferred from the product).
- **Devin in Slack**: a short result; the detail sits in its worklog, linked.
- **OpenClaw**: an oversized reply is split into chunks of the channel's size.
- **Telegram Bot API**: one text message holds at most 4,096 characters; longer
  text has to be split by the sender.

The ones that keep a chat readable keep the message short and whole and move the
detail behind a link or file. None of them asks for a short version in a fixed
shape, because none of them rewrites; Coffer does, so it has to say what shape
the rewrite takes.

## Options Considered

### Option A — Keep 5 lines (status quo)

- Pros: nothing to change; the shortest chat message.
- Cons: the reported problem. Five lines cannot carry a conclusion, its evidence
  and a next step, so summaries lose their structure.

### Option B — 12 lines in a fixed shape; the bound stays 20 lines (chosen)

The short version is asked for at most 12 lines with text (blank lines not
counted) and 1,500 characters, in a shape the prompt spells out: the conclusion
on the first line; then a few short groups in the long reply's own order, each a
label line followed by one-line `- ` items; a blank line between groups; no long
paragraphs; only formatting the chat renders. It ends with one line offering the
full report. The bound that triggers the rewrite is unchanged.

- Pros: a conclusion plus three groups of two or three points fits in about 12
  lines, about one phone screen; the shape keeps the answer scannable and is the
  same on every chat (a label line, not a Markdown heading, so it reads the same
  where headings do not render); one constant and one prompt change.
- Cons: a very rich report still loses detail in the chat; the reader asks for
  the file. The shape is a request to a model, not a guarantee; the rewrite is
  never held back again, so a model that ignores it still lands a longer reply.

### Option C — 20 lines, with the bound raised to 25

The first version of this change, chosen on 2026-11-25 and then reconsidered by
the owner the same day ("is 20 to 25 lines too many?").

- Pros: more detail survives in the chat.
- Cons: 20 lines of text plus blank lines between groups needs scrolling on a
  phone; it moves the bound for every reply, not only rewrites, for no reported
  problem with the bound.

### Option D — Bound by characters only, split longer text across messages

- Pros: no line counting.
- Cons: a split reply reads as several messages where the owner wants one, and
  brings back "half a message"; Telegram's 4,096 limit forces a split, and
  SeaTalk's was not checked.

### Option E — Line budget as a per-channel setting

- Pros: each owner and platform can tune it.
- Cons: a setting nobody has asked to tune; Coffer adds no setting a fixed default
  can settle.

## Decision

Option B. `application/channel/reply_rewrite.py` keeps the bound at
`MAX_REPLY_LINES` = 20 and `MAX_REPLY_CHARS` = 1,500, and asks for the short
version in at most `REWRITE_MAX_LINES` = 12 lines in the shape above. The number
is a constant, not a setting.

## Consequences

- A condensed answer arrives as a conclusion plus labelled groups, one phone
  screen long.
- Replies up to 20 lines or 1,500 characters are sent as the agent wrote them,
  as before.
- The rest of the answer is still in the agent's session; the owner asks for the
  file when the short version is not enough.
