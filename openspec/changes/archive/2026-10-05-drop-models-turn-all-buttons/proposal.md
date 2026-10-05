## Why

The **Turn all on** / **Turn all off** buttons added to a provider's Models section
(add-bulk-model-toggle) are dropped: the per-model switches and the search are enough.

## What Changes

- The Models toolbar no longer carries **Turn all on** and **Turn all off**; the
  paragraph and its bulk-toggle scenario are removed from provider-switching.

## Impact

- Frontend: `ProviderModels.tsx`, `ModelsToolbar.tsx`, `useModelCuration.ts`, en/zh strings.
- Specs: provider-switching.
- Docs: guides/providers (en + zh).
