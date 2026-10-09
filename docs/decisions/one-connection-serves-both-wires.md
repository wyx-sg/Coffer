# One Connection Serves Both Wires: an Optional Anthropic Address Beside the Base URL

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [A Connection Reaches the Agents Its Addresses Serve; No Scope, No Off Switch](provider-reach-is-what-its-addresses-serve.md), [LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md), [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](api-key-providers-are-reached-through-a-separate-local-model-proxy.md), spec provider-switching "Give a connection an Anthropic address", spec provider-switching "Ask for addresses, not a protocol", spec provider-switching "Fill in the Anthropic address of an existing connection", spec provider-switching "Test a connection on the wire the agent speaks", research note [provider switching](../research/provider-switching.md)

## Context

Claude Code speaks only the Anthropic Messages wire. Codex speaks only the
OpenAI Responses wire. A connection was `protocol` + `base_url` + a secret. The
local model proxy relays each agent's request unchanged to
`upstream_root(base_url) + path`, where the path is the agent's own wire
(`/v1/messages` for Claude Code). That works for a gateway that serves both
wires under one root, such as LiteLLM, OpenRouter or a company gateway.

Many vendors serve the Anthropic wire at a different root from their
OpenAI-compatible one. DeepSeek uses `https://api.deepseek.com` and
`https://api.deepseek.com/anthropic`. Kimi, Zhipu GLM, MiniMax, Qwen, Fireworks,
Baidu Qianfan and Tencent Hunyuan follow the same pattern. Their documentation
was checked on 2026-10-09; the addresses are in
`frontend/src/lib/providers/presets.ts`.

The incident (2026-10-07): a DeepSeek connection was saved with protocol
`openai` at `https://api.deepseek.com` and switched onto Claude Code. The proxy
sent Claude Code's requests to `https://api.deepseek.com/v1/messages`, DeepSeek
answered 404, and every Claude Code turn failed with "There's an issue with the
selected model". The connection test before the switch passed, because it
probed the connection's own protocol, not the wire Claude Code would use. We
reproduced it on the user's machine.

Two questions follow:

- How does a vendor whose wires live at two roots reach both agents?
- How does a mismatch get caught before the switch rather than after it?

The second question has one answer under every option: the switch test speaks
the agent's wire, at the address that wire goes to. This ADR decides the first.

A first version of this decision chose Option B below (a connection per wire).
The user rejected it once they saw it meant adding DeepSeek twice: "其他产品也会这样要求建2次吗？我感觉不应该这么麻烦吧". This
version replaces it.

## Options Considered

### Option A — An optional Anthropic address on the connection (chosen)

`ProviderConfig` gains `anthropic_base_url`. The proxy uses it for the
Anthropic wire and `base_url` for the other one. Presets fill it.

- **How others do it:** cc-switch keeps a separate provider list per app
  (Claude Code, Codex), and each app's DeepSeek preset fills that app's URL. The
  person still adds the account once per app, but from a preset that knows the
  right root. Coffer manages both agents from one library, so the equivalent of
  "fill the right root per agent" is one entry with both roots.
- **Pros:**
  - One row per vendor account, one key, one curated model set for both agents.
  - The DeepSeek-style vendors work from both agents with no extra step.
  - A gateway that serves both wires at one address takes the same address
    twice, so it fits the same shape.
- **Cons:**
  - Every place that reads "the endpoint" has to pick one of two:
    - the proxy member and the connection test pick by wire;
    - the secret destination names both addresses, so a key approved for one
      address waits again for a new second one;
    - the stored-key gate accepts either address;
    - listing, price lookup and the reported-price store keep `base_url`.
  - The two roots could list different models. In practice the vendors serve
    the same catalogue on both.
- **Why it wins:** the cost is in a handful of consumers, and the person pays
  nothing for it. Option B's cost lands on every person who uses one of these
  vendors from both agents.

### Option B — A second connection per wire root (the first version)

The DeepSeek-for-Claude-Code connection is its own `provider` resource:
protocol `anthropic`, base URL `https://api.deepseek.com/anthropic`, sharing
the stored secret.

- **How others do it:** opencode configures a provider per SDK package, so an
  Anthropic-compatible endpoint and an OpenAI-compatible one are two providers.
- **Pros:**
  - The connection model, the proxy and the projection stay as they are.
  - What a connection points at is one fact.
- **Cons:**
  - Two rows for one vendor account.
  - Curation (offered models, prices, windows) is done twice.
  - People have to know that they need the second connection. They find out
    only after the first one fails under Claude Code.
- **Why it loses:** the user rejected it as too much work for something
  comparable products do in one step.

### Option C — Translate between wires in the proxy

Claude Code's Messages request is translated to Chat Completions for an
OpenAI-only connection, and the reply is translated back. Claude Code Router and
LiteLLM do this.

- **Pros:**
  - Any OpenAI-compatible endpoint works under Claude Code, including vendors
    with no Anthropic wire at all (OpenAI, Gemini, Mistral, Groq).
- **Cons:**
  - The proxy ADR rules this out ("no protocol translation; adding it is a new
    decision"). The proxy relays bytes so that usage metering and logging stay
    exact.
  - Translators have a record of mangling tool calls, thinking blocks and
    streaming events.
  - Every new Claude Code feature becomes a translation gap.
- **Why it loses:** the vendors in question already serve the Anthropic wire
  natively. Someone who wants a translation can put LiteLLM in front and add it
  as Custom.

### Option D — Derive the Anthropic root from a known-vendor table at run time

Leave the stored base URL alone, and have the proxy rewrite
`api.deepseek.com` to `api.deepseek.com/anthropic` for the Anthropic wire.

- **Pros:**
  - No new field and nothing for the person to fill.
- **Cons:**
  - The URL the key is sent to differs from the one the person saved and
    approved. That breaks the rule that a key goes only to a destination a
    person approved.
  - The table has to track vendors' URL changes in releases.
  - Nothing on screen shows where requests actually go.
- **Why it loses:** it hides the destination, which is what the secret boundary
  exists to make visible. Option A uses the same vendor table, but only to fill
  a field the person can see and edit.

## Decision

A remote `openai` connection may carry an Anthropic address. The proxy sends the
Anthropic wire there and every other wire to `base_url`. The key's approved
destination names both addresses. The switch test for Claude Code speaks the
Anthropic wire at the Anthropic address, else at the base URL.

The Add and Edit dialogs ask for addresses, not a protocol: an
OpenAI-compatible address (Codex) and an Anthropic-compatible address (Claude
Code). The stored protocol follows: an OpenAI address makes the connection
`openai` with the Anthropic address as its second; an Anthropic address alone
makes it `anthropic`. The user asked for this once the second address existed:
"自定义这里是不是不用选协议了". A preset fills the addresses its vendor documents.

Rules that follow:

- Only a remote `openai` connection takes a second address. A local runtime
  serves the wires detection found at one address.
- The proxy still translates nothing.
- A preset names an Anthropic address only where the vendor documents one for
  Claude Code.

## Consequences

- `ProviderConfig.anthropic_base_url`, `served_wires()` and `base_url_for()`
  are in `backend/coffer/domain/provider/config.py`. The proxy member is in
  `application/provider/proxy_state.py`, the destination in `secret_gate.py`,
  and the stored-key gate in `introspection_gate.py`.
- Existing connections are migrated at startup by
  `application/provider/anthropic_address.py`:
  - a gateway Claude Code runs on gets its own base URL;
  - a DeepSeek connection Codex does not run on gets DeepSeek's Anthropic
    address, whose key then waits for approval.
- An `anthropic` connection that Codex ran on through a gateway is not
  migrated, because its wire can't be edited under a running agent. Its Codex
  agent falls back to its own login, and the person re-adds the gateway's
  OpenAI address in Edit.
- Frontend:
  - `lib/providers/addresses.ts` maps addresses to the stored shape;
  - `AddressInputs.tsx` is shared by `AddEndpointStep.tsx` and
    `EditProviderDialog.tsx`;
  - `probeEndpoint` in `lib/hooks/useModelSwitchTest.ts` is the switch test.
