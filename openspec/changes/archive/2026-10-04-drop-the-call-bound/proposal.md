## Why

Speech-to-text transcription is now the only model call Coffer makes. A
per-call time limit that an operator can set, with a range, a refusal at the
route and a clamp in a pass, is a whole setting built for a family of calls that
no longer exists. One fixed limit serves the one call that remains.

## What Changes

- Transcription runs under a fixed 60 second limit. The `model_timeout_s`
  setting, `PUT /api/v1/internal-engine-config/timeout`, and the `model_timeout_s`
  and `default_model_timeout_s` fields of the settings answer are gone.
- A stored `model_timeout_s` key is ignored on read and dropped on the next
  write, like the other retired keys.
- The Call bound row leaves Settings › General; the Speech-to-text section keeps
  the speech-to-text picker and the price-refresh switch.

## Impact

- Specs: internal-engine, web-ui, vault-sync.
- Code: the internal-engine settings, repo, service and routes; the speech-to-text
  transcriber wiring; Settings › General.
- Docs: configuration reference, provider and Web UI guides, glossary, and the
  internal-engine settings ADR (English and Chinese).
