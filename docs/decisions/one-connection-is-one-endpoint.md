# One Connection Is One Endpoint; a Vendor That Serves Two Wires at Two Roots Is Two Connections

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md), [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](api-key-providers-are-reached-through-a-separate-local-model-proxy.md), spec provider-switching "Offer a vendor's Anthropic endpoint as its own connection", spec provider-switching "Test a connection on the wire the agent speaks", research note [provider switching](../research/provider-switching.md)

## Context

Claude Code speaks only the Anthropic Messages wire. Codex speaks only the
OpenAI Responses wire. A connection is `protocol` + `base_url` + a secret, and
its reach is a per-agent scope, so one connection can be scoped to both agents.
The local model proxy relays each agent's request unchanged to
`upstream_root(base_url) + path`, where the path is the agent's own wire
(`/v1/messages` for Claude Code). That works for a gateway that serves both
wires under one root, such as LiteLLM, OpenRouter or a company gateway.

Several vendors serve the Anthropic wire at a different root from their
OpenAI-compatible one. DeepSeek uses `https://api.deepseek.com` for OpenAI and
`https://api.deepseek.com/anthropic` for Anthropic. Moonshot, Zhipu and MiniMax
follow the same pattern.

The incident (2026-10-07): a DeepSeek connection was saved with protocol
`openai` at `https://api.deepseek.com` and switched onto Claude Code. The proxy
sent Claude Code's requests to `https://api.deepseek.com/v1/messages`, DeepSeek
answered 404, and every Claude Code turn failed with "There's an issue with the
selected model". The connection test before the switch passed, because it
probed the connection's own protocol (`/chat/completions`), not the wire
Claude Code would use. We reproduced it on the user's machine: the stored key
returns 404 on the Anthropic wire at the saved base URL and passes on the OpenAI
wire.

Two questions follow:

- How does a vendor whose wires live at two roots reach both agents?
- How does a mismatch get caught before the switch rather than after it?

The second question has one answer under every option below: the switch test
speaks the agent's wire (Anthropic for Claude Code on any connection). This ADR
decides the first.

## Options Considered

### Option A — A second connection per wire root (chosen)

The DeepSeek-for-Claude-Code connection is its own `provider` resource: protocol
`anthropic`, base URL `https://api.deepseek.com/anthropic`. It can pick the same
stored secret the OpenAI connection uses, because every secret field supports
picking an existing secret. The Add dialog's preset for such a vendor offers
both wires, and picking one fills the matching root.

- **How others do it:** cc-switch keeps one provider list per app (Claude Code,
  Codex), and its DeepSeek entry for Claude Code is the `/anthropic` URL. opencode
  configures a provider per SDK package, so an Anthropic-compatible endpoint and
  an OpenAI-compatible one are two providers with their own `baseURL`.
- **Pros:**
  - The connection model, the proxy and the projection stay as they are.
  - What a connection points at is one fact you can read in one place.
  - The connection test, model listing and price lookup each have exactly one
    endpoint to use.
- **Cons:**
  - Two rows for one vendor account.
  - Curation (offered models, prices, windows) is done twice if both are used.
- **Why it wins:** the cost lands only on the vendors that split their roots,
  and only for people who use both agents there. Combined with the
  agent-wire test, a wrong choice fails before the switch rather than after it.

### Option B — An optional Anthropic base URL on every connection

`ProviderConfig` gains `anthropic_base_url`. The proxy uses it for the Anthropic
wire and `base_url` for the other one. Presets fill it.

- **Pros:**
  - One row per vendor account.
  - One curated model set shared by both agents.
- **Cons:**
  - Every place that reads "the endpoint" has to pick one of two: the
    connection test, listing, the price lookup by base URL, the reported-price
    store keyed by root, the SSRF and secret-destination checks (a key approved
    for one URL must now be approved for two), the proxy's member, and the
    usage records.
  - The form grows a field most connections leave empty.
  - The two roots can list different models, so a single curated set can be
    wrong for one of them.
- **Why it loses:** it widens a core document and every consumer of it to
  serve a handful of vendors. Option A serves those same vendors with no
  schema change.

### Option C — Translate between wires in the proxy

Claude Code's Messages request is translated to Chat Completions for an
OpenAI-only connection, and the reply is translated back. Claude Code Router and
LiteLLM do this.

- **Pros:**
  - Any OpenAI-compatible endpoint works under Claude Code, including vendors
    with no Anthropic wire at all.
- **Cons:**
  - The proxy ADR rules this out ("no protocol translation; adding it is a new
    decision"). The proxy relays bytes so that usage metering and logging stay
    exact.
  - Translators have a record of mangling tool calls, thinking blocks and
    streaming events.
  - Every new Claude Code feature becomes a translation gap.
- **Why it loses:** the vendors in question already serve the Anthropic wire
  natively. Translation would buy reach to endpoints that don't, at the cost of
  correctness for all of them.

### Option D — Derive the Anthropic root from a known-vendor table

Leave the stored base URL alone, and have the proxy rewrite
`api.deepseek.com` to `api.deepseek.com/anthropic` for the Anthropic wire.

- **Pros:**
  - No new row and no new field.
- **Cons:**
  - The URL the key is sent to differs from the one the person saved and
    approved. That breaks the rule that a key goes only to a destination a
    person approved.
  - The table has to track vendors' URL changes in releases.
  - Nothing on screen shows where requests actually go.
- **Why it loses:** it hides the destination, which is what the secret boundary
  exists to make visible.

## Decision

A connection is one endpoint: one protocol at one base URL. A vendor that serves
the Anthropic wire at a different root is reached from Claude Code through a
second connection, which may share the first one's stored secret. Presets for
such vendors name both roots, and the Add dialog fills the one matching the
picked wire. The connection test behind a switch speaks the wire the agent uses,
so an endpoint that does not serve that wire fails before the switch can be
reviewed.

Rules that follow:

- `ProviderConfig` carries no second address. A per-wire URL is a new decision
  that has to answer Option B's costs.
- The proxy still translates nothing.
- A preset gets `anthropicBaseUrl` only when the vendor documents an
  Anthropic-compatible root.

## Consequences

- Presets: `frontend/src/lib/providers/presets.ts` (`anthropicBaseUrl`,
  `presetBaseUrl`). `vendorOf` reads either root as the vendor.
- The Add dialog: `AddEndpointStep.tsx` shows the protocol cards for Custom and
  for any vendor with two roots.
- The agent-wire test: `probeProtocol` in
  `frontend/src/lib/hooks/useModelSwitchTest.ts`, used by the Change model
  dialog and Overview › Model › Test.
- Someone who uses DeepSeek from both agents keeps two connections and curates
  each. That is the accepted cost.
