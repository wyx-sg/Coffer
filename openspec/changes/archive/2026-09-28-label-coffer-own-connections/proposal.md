## Why

The Model providers library marked the speech-to-text connection with a bare "Speech to text" pill,
which reads as something the provider can do rather than a job Coffer gives it, and it did not mark
the connection Coffer's own background model runs on at all. The "Active" pill's hint also claimed it
meant Coffer's own model, when it means an agent is switched to the connection.

## What Changes

- The library row and the detail header mark the `internal_default` connection "Coffer · background
  model" and the `transcribe_default` connection "Coffer · speech to text", each with a hint naming
  where it is changed.
- The "Active" pill's hint says an agent is switched to the connection.

## Impact

- `provider-switching` — "Offer every connection operation on REST, CLI and web".
- Frontend only: `CofferUseBadge` replaces `TranscribeProviderBadge`; en/zh strings.
