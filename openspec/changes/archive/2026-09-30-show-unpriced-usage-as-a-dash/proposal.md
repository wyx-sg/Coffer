## Why

The Usage page had no prices for OpenAI (Codex) models. Anthropic's rates are bundled in the price snapshot from Anthropic's own published pricing. Coffer has no equivalent verified source for OpenAI's rates, so none are bundled, and a bundled rate from anywhere else would be a guess. A model with no price read "No price" on the page and `~$0.0000 (+N unpriced)` in `coffer usage`; the second looks like a cost of zero.

## What Changes

- No OpenAI rates are added to the snapshot. The requirement now states that the snapshot carries only rates from the vendor's own published pricing, and that OpenAI's are absent for want of a verified source.
- Where nothing in a cost is priced, the Usage page and `coffer usage` show `—`. On the page the dash's tooltip and accessible name say that Coffer ships Anthropic's rates only and that a price is set on the connection in Model providers. `coffer usage requests` shows `—` for an unpriced request.
- A price set on the connection still prices any model, Codex models included.

## Capabilities

### New Capabilities

### Modified Capabilities
- `provider-switching`: how an unpriced cost is shown, and which rates the snapshot may carry.

## Impact

- Frontend: `components/usage/UsageCells.tsx`, `components/usage/UsageTiles.tsx`, `i18n/locales/{en,zh}.json`, the Usage page test.
- Backend: `surfaces/cli/usage_cmd.py`.
- Docs: the usage guide.
- Design canvas: the System canvas's Usage boards.
