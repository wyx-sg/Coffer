# Send a channel's full report only when asked

## Why

Coffer's default reply style tells a channel-driven agent to end a reply that
needs a full report by asking "do you want the full report?". The vault skills
that write investigation reports say the opposite — deliver the detailed report
only when the reader asks, never offer it routinely — and a reply too long for a
chat already gets a **📄 Full report** button. The model reads both and picks
one at random, and an offer at the end of every report reads like a form
letter, not like a person.

## What Changes

- Coffer's default reply style asks for a full report only as a Markdown file,
  and only when the reader asks for it; a reply never ends by offering one.
- The follow-up that asks for the short version of a too-long reply no longer
  tells the agent to end by asking about the full report: the **📄 Full report**
  button under that reply is the offer.
- Docs (English and Chinese), the ADR on long channel replies and the specs say
  the same.

## Impact

- `backend/coffer/domain/chat/channel_prompt.py` (`DEFAULT_REPLY_STYLE`)
- `backend/coffer/application/channel/reply_rewrite.py` (`rewrite_prompt`)
- An owner's own rewritten reply style is untouched; the channel page already
  says when Coffer's default has changed since it was written.
