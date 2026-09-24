## Why

SeaTalk splits a button row evenly across the card, and the card is only as
wide as its body. Rows of three cut long labels: the `/agent` card showed
"Claude C…" and the `/model` card showed "claude-fable-5-…".

## What Changes

- channels/seatalk: how many buttons share a row depends on their labels. A row
  takes the next button only while every label in it fits the width a row of
  that size leaves, measured in display columns (a CJK character counts two).
  A long label gets a row of its own. When that would need more than three
  rows, the buttons are spread evenly over three rows.

## Capabilities

### New Capabilities

### Modified Capabilities

- `channels/seatalk`: "Build cards in SeaTalk's published element shape" lays
  buttons out by label width.

## Impact

`seatalk_parse.button_rows` replaces the fixed rows of three in
`interactive_card`.
