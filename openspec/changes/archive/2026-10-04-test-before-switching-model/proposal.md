## Why

The Change model dialog went straight from Provider and Model to Review changes
and Apply. A provider that does not answer, or does not serve the chosen model,
was only found after the agent's files were written, and a failed test during
the review was a warning that did not stop the apply.

## What Changes

- The dialog tests the chosen provider with the chosen model by itself (debounced,
  stale runs cancelled) and shows the result as a line under Model: Testing
  connection…, Connection OK with its duration, or Connection failed with the
  reason and Retry.
- Review changes is enabled only when the draft differs, names a model and the
  test for exactly that provider and model passed. The built-in login needs no test.
- The review no longer runs its own test.

## Impact

- Frontend: `components/agents/model/` (dialog, fields, `ModelTestStatus`),
  `lib/hooks/useModelSwitchTest.ts`, `useModelSwitch.ts`.
- Backend: none; the test is the existing `POST /api/v1/models/test-connection`.
- Specs: provider-switching.
- Docs: guides/providers, guides/agents (en + zh).
