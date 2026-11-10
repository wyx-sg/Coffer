# A Channel Reply Is Plain Text, With No Card or Button

**Status**: Accepted
**Date**: 2026-11-10
**Deciders**: Yuxing Wu
**Related**: [A Channel Turn Posts Nothing Until It Is Done, and the Reply Is the Answer Alone](channel-live-surface-strategy.md), [A Long Channel Reply Is Rewritten Short by the Agent](long-channel-reply-is-rewritten-short.md), [Channel `/help` Is a List to Read, and a Card Carries Only the Buttons That Act on It](channel-help-is-a-list-and-cards-carry-only-their-own-actions.md), [Ask in the Reply, Not in a Card](ask-in-the-reply-not-in-a-card.md), spec channels "Withdraw a bot reply on the owner's command", "Ask for the short version of a reply too long for a chat", spec channels/seatalk "Send every reply as text"

## Context

Until 2026-11-10 an agent's reply could carry buttons, and on SeaTalk any
message with buttons is an interactive card:

- Every reply in a **group** carried a 🗑 button, on Telegram as an inline
  button under the text, on SeaTalk as a card. SeaTalk has no API to delete a
  bot's message and can rewrite only cards (Update Message, 7 days, sender
  only), so a SeaTalk group reply was *always* a card: that was what let the
  owner withdraw it, by rewriting it into a "🗑 Withdrawn" card.
- The short version of a reply that was too long carried a **📄 Full report**
  button, in direct chats too, so on SeaTalk it was a card as well.

The owner, who mostly uses SeaTalk, asked on 2026-11-09 for the bot to stop
answering in cards and reply in ordinary text, the way a person does. Asked
how far to go, the owner chose to change the agent's replies only and keep the
cards that commands answer with (`/status`, `/new`, `/model`, `/dir`,
`/resume`) and the Continue and Discard buttons after `/stop`.

How comparable bridges treat buttons on a reply (their public docs, 2026-11;
see [the IM bridges survey](../research/im-agent-bridges.md)):

- **Claude Code Channels** (Telegram, Discord, iMessage): the answer is text;
  buttons appear only on permission prompts, and even those can be answered by
  typing `yes <id>`.
- **Hermes**: replies are text; native buttons only where the platform has them,
  and every action also has a typed command (`/approve`, `/deny`, `/discard`).
- **OpenClaw**: replies are text; approvals have buttons and a typed
  `/approve <id> <decision>`.
- **claude-code-telegram**: replies and even lists are text; one command has
  buttons.
- **cc-connect**: the counter-example, with progress and approval cards on
  Feishu, DingTalk and Slack.
- **People in a chat** answer in text and offer choices as "1, 2 or 3?".

The common pattern: the answer is text, and buttons, where they exist at all,
sit on a control surface, never on the answer.

## Options Considered

### Option A — Replies are plain text everywhere; commands keep their cards (chosen)

Every reply goes out as ordinary text in direct chats and groups, with no 🗑
and no 📄. The short version of a too-long reply ends with one line offering the
full report, and the owner asks for it in a message. `/del` keeps withdrawing
on a transport that can delete a bot's message (Telegram); on SeaTalk, which
can neither delete nor rewrite text, the transport declares a withdraw window
of 0 and `/del` answers "🗑 This chat cannot withdraw bot replies.". Command
answers keep their cards and buttons.

- Pros: the chat reads like a conversation with a person, which is what the
  owner asked for; SeaTalk group replies render tables and long text as a text
  message does (a card description renders neither tables nor more than four
  1,000-character blocks); the 🗑 and 📄 tap paths, SeaTalk's card withdrawal
  and the `withdraw_removes` capability are deleted, so there is less to keep.
- Cons: a SeaTalk reply can no longer be taken back at all, in a group either;
  the owner's only safeguard there is not asking the bot in a group what it
  should not say. Asking for the full report costs typing a line instead of a
  tap.

Wins because it is what the owner chose, and the cost falls on a safeguard the
platform itself does not offer for text.

### Option B — All of it in text: replies, command answers, the held line

As A, and also `/model`, `/dir` and `/resume` answer with numbered lists
(`/model 2`), `/status` and `/new` in text, and the messages held after `/stop`
are continued by any message and discarded by a second `/stop`. The button and
card machinery would be deleted entirely.

- Pros: one rendering path for everything; the most code removed.
- Cons: the commands lose one-tap choices that do help on a phone; a larger
  change to commands the owner had reviewed and agreed to on 2026-10-20.

Lost on the owner's choice: the request was about how the bot answers, and
command cards are a control surface, not an answer.

### Option C — As A, but a SeaTalk group reply stays a card

- Pros: keeps withdrawing on SeaTalk groups.
- Cons: the group replies are exactly the cards the owner asked to be rid of.

### Option D — Keep the cards (the design this replaced)

- Pros: withdrawing works on every transport; the full report is one tap away.
- Cons: the chat is full of cards, which is what prompted the change.

## Decision

Option A. `ReplyTracker` sends a reply with no buttons and records it only on a
transport with a withdraw window (`application/channel/reply_tracking.py`);
SeaTalk declares `withdraw_window_hours=0` and Telegram 48. `/del` on a
transport with no window says it cannot withdraw. The rewrite prompt asks the
short version to end with an offer of the full report
(`application/channel/reply_rewrite.py`). A tap on a 🗑 (`del:`) or 📄
(`full:`) button still on an old message does nothing.

## Consequences

- The reply ledger only ever holds Telegram replies; its retention drops from
  eight days to three.
- The channel adapter port loses `withdraw_message`; withdrawing is
  `delete_message`.
- Cards remain for command answers and the held line, so the selection-card,
  card-update and SeaTalk interactive-card code stays.
