## Why

A provider's Models section had one switch per model, so narrowing or widening
a long endpoint list (dozens of models) meant one click each.

## What Changes

- The Models toolbar gains **Turn all on** and **Turn all off**. They act on the
  rows the search and Type filter match, in one write, keeping prices and types.
- **Turn all off** is refused (disabled, with a tooltip) when it would leave no
  model on, since an empty selection means "no restriction".

## Impact

- Frontend: `components/providers/ProviderModels.tsx`, `ModelsToolbar.tsx`,
  `useModelCuration.ts`, en/zh strings.
- Specs: provider-switching.
- Docs: guides/providers (en + zh).
