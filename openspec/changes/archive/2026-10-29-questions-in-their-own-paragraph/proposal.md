# Put a channel question in its own paragraph

## Why

A channel reply ran what the agent had done and what it needed into one
paragraph ("The ticket draft is ready … What effort estimate should I enter?"),
so the reader had to hunt for the question. The owner wants the question set
apart, and several questions numbered, so they can be seen and answered at a
glance.

## What Changes

- The channel note asks for questions in their own paragraph after what was
  done, numbered 1, 2, 3 when there are several.

## Impact

- `domain/chat/channel_prompt.py`, its unit test, the channels guide (en, zh).
