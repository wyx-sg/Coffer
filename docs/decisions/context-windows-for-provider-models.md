# A Provider Model's Context Window Comes From You, Then the Endpoint, Then the Bundled List, Else Nothing

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md), [Usage Is Metered at the Proxy; Subscription Agents Are Not Metered](usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota.md), spec provider-switching "Resolve each provider model's context window", spec provider-switching "Tell Claude Code a provider model's window", spec provider-switching "Record a context window with each curated model", research note [provider switching](../research/provider-switching.md)

## Context

Agents compact a conversation as it approaches the model's context window, so
they need the right window for the model they run on.

- **Claude Code** knows Claude ids itself. For any other id it prints that the
  model "isn't described by this version's model catalog", assumes 200k, and
  compacts there. That happened in practice with `agnes-2.5-pro-alpha` through a
  gateway. The only lever is `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS`. We read Claude
  Code's source to confirm the variable silences the warning for an unknown id
  and does not affect a Claude id. It is one value per session, not per model.
- **Codex** reads `context_window` per entry from the model list Coffer writes.

Where can a window come from?

- **Endpoint metadata** comes from Anthropic's `/v1/models` (`max_input_tokens`),
  OpenRouter (`context_length`, `top_provider.context_length`), some gateways
  and vLLM (`context_window`, `max_model_len`), and local runtimes. Most
  OpenAI-compatible endpoints report nothing.
- **The bundled price list** (pydantic genai-prices, which Coffer already ships
  and refreshes daily for pricing) records `context_window` for 934 of its 1737
  models. It is provider-scoped, like its prices.
- **The person**, who can read the vendor's model card.

How comparable tools handle it:

- **Manual window field per model:** Cline, Roo Code, Zed and Continue.
- **A public catalogue, with the user able to override it:** Kilo Code and
  opencode use models.dev; Aider uses LiteLLM's model map.
- **A fixed assumption with no override:** Cursor assumes a large window for
  custom models. This is the most complained-about of the four approaches.

## Options Considered

### Option A — You set → endpoint → bundled list → nothing, for the model the agent is bound to (chosen)

One resolver (`domain/provider/model_window.py`,
`application/provider/windows.py`) answers both the projection and the Models
tab:

1. The `user_context_window` the person set on the curated entry.
2. The `context_window` the endpoint reported, kept on the curated entry when
   the model was switched on.
3. The bundled list's window for the model at the provider the base URL
   belongs to.
4. Otherwise unknown, and nothing is written.

Claude Code gets the bound model's window. Codex gets each listed model's own
window. The Models tab shows each window with its source and offers
**Set window…** and **Reset to default**, the same way prices work.

- **Pros:**
  - Correct windows with no typing for most known models, because endpoint
    metadata and the bundled list cover them.
  - A person can always correct a wrong value or fill a missing one.
  - Unknown stays unknown, so Claude Code falls back to its own behaviour rather
    than to a guess Coffer made up.
  - No new data source and no network call: the list is already shipped and
    refreshed.
- **Cons:**
  - A list entry can lag a vendor's change. The source label makes that visible,
    and "You set" overrides it.
  - Claude Code's window is per session, so a model picked later with `/model`
    keeps the projected model's window until the next projection.
- **Why it wins:** it matches the tools people rate best: a catalogue plus an
  override, with endpoint metadata where it exists. It reuses data Coffer
  already carries.

### Option B — Manual entry only

- **Pros:** the simplest to build, and always what the person said.
- **Cons:** every model needs typing, and most people won't, so Claude Code
  keeps assuming 200k.
- **Why it loses:** the window is already known for most models. Asking for it
  by hand discards that.

### Option C — Endpoint metadata only (the design this replaced)

The connection recorded only what the endpoint reported; the person never chose
a context window.

- **Pros:** never wrong about what this endpoint serves.
- **Cons:** most OpenAI-compatible endpoints report nothing, and DeepSeek, Agnes
  and most relays fall through.
- **Why it loses:** it leaves the common case unsolved.

### Option D — Fetch models.dev (or LiteLLM's map) at run time

- **Pros:** broad and current coverage.
- **Cons:**
  - A second external catalogue next to the one already shipped.
  - A network dependency, and its own refresh and failure handling.
  - Model ids keyed differently from the price list, so price and window could
    disagree about which model an id is.
- **Why it loses:** the bundled list already covers windows and is matched by
  the same provider-scoped rules as prices.

### Option E — Assume a large window for every non-Claude model

- **Pros:** nothing to resolve.
- **Cons:** an overestimate makes the agent overrun the real window and fail
  mid-turn. That is worse than compacting early, and it is the behaviour users
  complain about in Cursor.
- **Why it loses:** a wrong guess is worse than no answer.

### Option F — Tell Claude Code the smallest window among the connection's models

Since `CLAUDE_CODE_MAX_CONTEXT_TOKENS` is per session, write the minimum, so
that any model picked later with `/model` is safe.

- **Pros:** never overestimates after a `/model` switch.
- **Cons:** one small model on the connection shrinks every session on it. A
  1M-window model would compact at 32k because a small model is also curated.
- **Why it loses:** the bound model is what the session starts on and what the
  person chose. The user picked "the model currently selected" when this was
  put to them.

## Decision

A provider model's context window resolves in this order: You set, then the
endpoint's report, then the bundled list's record, else unknown. One resolver
serves the projection and the Models tab. Claude Code is told the window of the
model it is bound to, and only for a non-Claude id. Codex is told each listed
model's window. An unknown window is never written and never guessed.

Rules that follow:

- The bundled list is the only built-in source of windows. A second catalogue
  is a new decision.
- The switch and the reconciler are given the same resolver, or they would
  disagree about the file.
- The person's value is stored as `user_context_window` beside the endpoint's
  `context_window`, so **Reset to default** can fall back to it.

## Consequences

- `CuratedModel.user_context_window` is part of the synced connection document.
  The endpoint's value stays on `context_window`.
- `BundledPrices.context_window(model, base_url=)` reads the list's window with
  the price lookup's provider scope.
- `POST /api/v1/providers/{uid}/windows` and the Models tab's Window column and
  dialog are in `ModelWindowCell.tsx`, `SetWindowDialog.tsx` and
  `useModelCuration.setWindow`.
- A refreshed price list can change a projected window. The reconciler then
  re-projects, as with any other parameter change.
