# The channel note forbids citing the agent's own instructions

## Why

A channel bot asking for an effort estimate wrote "create-ticket's SKILL.md
(/Users/…/SKILL.md) requires: 'Ask for missing effort…'". The rule against
this lived only in skills the agent loads on demand; the agent read it and
still broke it, and on that path the skill that needed it did not load it. The
owner's own reply style replaces Coffer's default, so the only text every
channel turn is sure to carry is the fixed channel note.

## What Changes

- The channel note tells the agent never to quote or name its skills,
  instructions or local file paths.
- The dialog sentence is shortened to keep the note inside its word budget.

## Impact

- `domain/chat/channel_prompt.py`, its unit test, the channels guide and chat
  architecture (en, zh).
