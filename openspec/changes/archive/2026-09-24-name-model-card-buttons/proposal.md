## Why

The `/model` card showed raw model ids, and SeaTalk cut the long ones.
`claude-fable-5-1[1m]`, the 1M-context Fable that Claude Code caches as an
extra option, showed as "claude-fable-5-…" next to the `fable` alias, so the
card seemed to offer the same model twice.

## What Changes

- channels: each `/model` button shows the model's name, or its id when the
  catalogue names none, and a 1M-context variant says "1M". The tap still
  carries the id.

## Capabilities

### New Capabilities

### Modified Capabilities

- `channels`: "Switch the model and reasoning effort from chat" names the card's
  buttons.

## Impact

`ModelSuggestionPort.model_labels` returns `{id: button text}` in catalogue
order. The model card reads its choices and their names from that one call.
