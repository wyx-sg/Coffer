## Why

A Codex turn in a SeaTalk group asked the owner a question, then finished
without waiting: Codex's code mode runs `coffer__ask` in a background `exec`
cell, polls it for about a minute, and moves on. The turn's end cancelled the
question, so its card turned into "⏹ Stopped" before the owner had read it, and
the agent's final reply asked the same thing again as plain text. The card also
carried no @mention, so the owner was not notified, and no 🗑, unlike every
other group reply. The options are argued in ADR
`a-question-outlives-the-turn-that-asked-it`.

## What Changes

- **A question outlives a turn that finished on its own.** Stopped, failed or
  shut down still cancels it. A question left open keeps its card and buttons;
  once answered, the answer reaches the agent as the conversation's next
  message, which starts a turn. A new question in the conversation cancels one
  an ended turn left open; one left open is given up on after 24 hours.
- **The channel note tells the agent to wait** for its question's answer, or to
  end its turn silently; the answer comes next.
- **Group question cards** open with an @mention of the asker and carry the 🗑,
  filed on their own and kept once the card is rewritten.

## Impact

- `application/chat/questions.py` (+ `question_turns.py`, split off),
  `turn_runner.py`; `application/channel/question_flow.py`,
  `question_card.py`, `turn_render.py`, `inbound.py`, `inbound_events.py`,
  `reply_tracking.py`; `domain/chat/channel_prompt.py`.
- Specs `chat` and `channels`, edited directly (`skip_specs: true`).
- docs-site guides `channels.md` (en, zh); design canvas for channel cards.
