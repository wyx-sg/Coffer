## Why

A conversation's title is the text of its first message, so `/status` showed a
bare grafana link as its first line (2026-11-05). The owner decided the title
does not belong on the card.

## What Changes

- `/status` no longer shows the conversation's title. Inside a parallel thread
  it still opens with the thread's `🧵#N` mark, which says which thread it is.

## Impact

- `status_card`; channels spec "Report the chat's state as a status card".
