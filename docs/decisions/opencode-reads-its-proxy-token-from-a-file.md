# OpenCode Reads Its Proxy Token From a File Coffer Keeps

**Status**: Accepted
**Date**: 2026-11-22
**Deciders**: Yuxing Wu
**Related**: [Cursor, OpenCode and DeepSeek Harness Are Supported Agents](cursor-opencode-and-deepseek-harness-are-supported-agents.md), [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](api-key-providers-are-reached-through-a-separate-local-model-proxy.md), [Only a Present Human Sees a Secret or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), [Provider Connections Are Projected Into Agent Config](provider-connections-projected-into-agent-config.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), spec provider-switching "Project into OpenCode config without overwriting it", spec provider-switching "Authenticate each agent to the proxy with its own local token"

## Context

A model connection reaches an agent through the local model proxy. The agent
calls `http://127.0.0.1:<port>`, authenticates with its own local proxy token,
and the proxy adds the provider key. Claude Code and Codex fetch that token
themselves. Claude Code runs `apiKeyHelper`, Codex runs its provider `auth`
command, and both commands are `coffer proxy token --agent-uid <uid>`. The
token never lands in their config files.

The token unlocks only the loopback proxy, on this machine, and it names the
agent for usage. It is not a provider key, and it is not a boundary against a
same-user process: anything that can read the agent's config can run the
token command. It keeps browser pages and other users' processes off the
proxy, and it attributes usage (ADR only-a-present-human-sees-a-secret-or-
sends-it-somewhere-new, rule 5).

OpenCode can use a custom provider with a base URL. Its documentation
([1.x](https://opencode.ai/v1/docs/providers.md),
[2.x](https://opencode.ai/docs/providers.md)) offers these ways to supply the
key, and no way to run a command for it:

- a literal string in `options.apiKey`;
- `{env:VAR}`, read from OpenCode's environment;
- `{file:path}`, the file's text read at startup;
- `/connect`, which stores the key in OpenCode's own
  `~/.local/share/opencode/auth.json`.

A local test on 2026-11-22 confirmed the shape Coffer writes. OpenCode 1.19.6
and 2.3.2 both load a 1.x `provider` block with `npm: "@ai-sdk/openai"`, read a
`{file:…}` key, and send `POST /openai/v1/responses` with `Authorization:
Bearer <file text>`. That is the route the proxy already relays for Codex, so
the proxy needs no new route.

## How comparable tools do it

- **LiteLLM, OpenRouter and other gateways.** Their OpenCode guides tell the
  user to put the gateway key in an environment variable and reference it
  with `{env:…}`, or to paste it with `/connect`.
- **OpenCode's own Poolside example.** It uses `"apiKey":
  "{file:~/.secrets/poolside-key}"`, a key file kept outside the config.
- **DeepSeek Harness.** Its `apiKeyEnv` is a credential reference that the
  harness resolves per request, "so no secret enters the configuration file".
- **Claude Code and Codex in Coffer.** Each runs a command, which OpenCode
  cannot do.

All of them keep the key out of the config file when they can.

## Options

### A. A token file Coffer keeps, referenced with `{file:…}` (chosen)

Coffer writes the agent's token to `~/.coffer/local/proxy-tokens/opencode`.
The directory is `0700`, the file is `0600`, and every write is an atomic
replace. `opencode.json` says `"apiKey": "{file:<that path>}"`. The secret
store stays the record of the token. The file is a copy that Coffer rewrites
when the token is minted or rotated, and deletes with the agent.

- Pro: `opencode.json` holds no secret, so sharing it, committing it to a
  dotfiles repo or pasting it into an issue leaks nothing.
- Pro: it works for an OpenCode the user starts in their own terminal, with
  nothing exported.
- Pro: rotation needs no config write. Coffer rewrites the file, and OpenCode
  reads it at its next start.
- Pro: `~/.coffer/local` is machine-local and never synced, like the token's
  secret-store ref.
- Con: the token exists in plaintext on disk. This changes little, because
  the same user could already print it with `coffer proxy token`, and the
  token unlocks only the loopback proxy.
- Con: OpenCode reads the file only when it starts, so a rotation reaches a
  running session only after a restart. Claude Code's helper cache has a
  similar delay of up to five minutes.

### B. The token as a literal in `opencode.json`

- Pro: the simplest option, with no extra file.
- Con: the token travels wherever the config goes, such as dotfiles repos,
  backups and shared snippets.
- Con: every rotation is a config write that goes through review, backup and
  the stale-file guard.
- Con: it breaks the rule that an agent's config names its key and does not
  hold it, which Claude Code and Codex both follow.

### C. `{env:COFFER_PROXY_TOKEN}`, set only when Coffer starts OpenCode

- Pro: nothing on disk.
- Con: an OpenCode started from the user's own terminal has no token and
  fails with 401. That is most OpenCode use, so the connection would look
  broken.

### D. Store the token through `/connect` in OpenCode's `auth.json`

- Pro: it is OpenCode's own key store.
- Con: Coffer would write into a file that holds the user's other provider
  keys, with no documented format to write it safely.
- Con: it is still plaintext on disk, and it is no better hidden than option A.

## Decision

Option A. OpenCode gets the provider projection that Claude Code and Codex
have. It is a `provider.coffer` block in `opencode.json` that points at the
proxy's OpenAI route and reads its key from the token file.

## Which agents get a model connection

- **OpenCode**: yes, by this decision.
- **Cursor**: no. `cursor-agent` runs only the models of the user's Cursor
  account and documents no custom endpoint. The editor's OpenAI base-URL
  override is kept in Cursor's own app state, not in a config file Coffer
  could project into.
- **Antigravity**: no. It runs only Google's hosted models (ADR
  antigravity-joins-at-its-config-layer-only).
- **DeepSeek Harness**: not yet. Its `@deepseek-ai/dsh-llm-pi-ai` adapter
  takes custom routes (`api: openai-responses`, a `baseURL`, and an
  `apiKeyEnv` credential reference). Coffer could add such a route in the
  block it already owns in `cordis.patch.yml`. Two questions are still open.
  First, how the credential reference resolves to the token without writing
  into dsh's `.credentials.yaml`, which holds the user's other keys. Second,
  how dsh selects a route's model as its default. These questions get their
  own investigation with a CI smoke test, as OpenCode's did.

## Consequences

- `ProxyTokenService` mirrors the token to a file for each agent whose
  projection declares `token_in_file`, which today is only OpenCode.
- OpenCode appears in a connection's `served_agents` whenever the connection
  has an OpenAI address, the same rule as for Codex.
- OpenCode's agent page shows the Model section, and the provider's **Used
  by** list can name OpenCode.
