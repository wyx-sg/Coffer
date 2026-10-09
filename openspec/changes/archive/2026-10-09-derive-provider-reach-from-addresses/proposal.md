## Why

DeepSeek serves the OpenAI wire at `https://api.deepseek.com` and the Anthropic
wire at `https://api.deepseek.com/anthropic`. The previous change asked people
to add the vendor twice, once per wire. The user rejected that ("其他产品也会这样要求建2次吗？"),
and chose one connection with two addresses. The user also chose to have the
agents a connection can serve follow from those addresses, and then to drop the
per-agent scope and the off switch entirely: which connection an agent runs on
is already the agent's own choice.

## What Changes

- A connection may carry an optional `anthropic_base_url` next to `base_url`.
  The proxy sends Claude Code's requests there and Codex's to `base_url`. The
  key is approved for both addresses.
- The Add and Edit dialogs ask for addresses, not a protocol: an
  OpenAI-compatible address (Codex) and an Anthropic-compatible address (Claude
  Code). The stored protocol follows from which ones are filled in.
- The agents a connection serves follow from its addresses (`served_agents` on
  every read). The per-agent scope and the enabled switch are gone from the
  provider kind and its pages. The header says which agents can use the
  connection.
- Startup migration:
  - an agent on a switched-off connection goes back to its own login, and the
    connection is switched on;
  - stored scopes are cleared;
  - an OpenAI connection Claude Code runs on gets its own base URL as its
    Anthropic address;
  - a DeepSeek connection Codex does not run on gets DeepSeek's Anthropic
    address.
- Sixteen more vendor presets with their documented addresses and marks, and a
  region choice for vendors whose mainland-China addresses differ.

## Impact

- Backend:
  - provider config (`anthropic_base_url`, `served_wires`)
  - targets (reach from addresses)
  - proxy state, secret destination, stored-key gate
  - switch refusal message
  - provider kind (`supports_scope=False`)
  - startup migrations, routes and schemas
- Frontend:
  - Add and Edit dialogs (address fields, region)
  - detail header and Endpoint section
  - presets and brand marks
  - the switch test's address
- Specs: provider-switching.
- ADRs: one-connection-serves-both-wires (replaces one-connection-is-one-endpoint) and provider-reach-is-what-its-addresses-serve.
- Docs: providers guide (en/zh).
- Canvas: Agents (Providers boards).
