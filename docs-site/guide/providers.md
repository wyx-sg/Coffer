# Model providers

Claude Code and Codex each read their endpoint and their key from their own config file, with their own key names. Pointing them at a gateway by hand means editing several files, leaving API keys in plaintext, and keeping no record of what changed. A **connection** is Coffer's answer: one named, credentialed endpoint, stored once, projected into the native config of each agent you route it at.

A connection is an **override, never a prerequisite**. An agent with nothing projected runs on its own built-in login, and no surface blocks on "no connection configured".

## A connection answers "which account", not "which model"

This is the one distinction the rest of the page rests on. A connection holds `{protocol, base_url, credential_ref, models}` — a gateway account, and which of its models you intend to use. It holds **no model it runs**. The model is chosen at the point of use and bound **per agent**:

```bash
coffer agent edit claude-code --model sonnet --fast-model haiku
coffer agent edit my-codex --model gpt-5.2
```

An **unbound agent projects no model at all** — the `ANTHROPIC_MODEL` key is omitted from Claude Code's settings, `model` is omitted from Codex's TOML — so the agent runs on its own default rather than on a name Coffer invented for it. `--clear-fast-model` unbinds the fast slot (an absent field and an explicit null mean different things; only the second one clears). `--wire-api` is Codex's, and `responses` is the only value Codex still loads.

A binding is a stored fact, not a write to disk. It reaches the agent's file the next time that agent's connection is activated — `coffer provider switch <name>` — because activation is the only operation that writes native config.

## Add a connection

```bash
coffer provider add my-gateway \
  --protocol openai \
  --base-url https://api.example.com/v1 \
  --secret "<paste-your-key>"
```

```
added provider my-gateway (openai)
```

`--protocol` says what the endpoint speaks. It drives model introspection and whether a key is required — it does **not** decide which agent the connection is written into:

| Protocol | What it means | Key | Starts reaching |
| --- | --- | --- | --- |
| `anthropic` | Anthropic's own wire. | Required | both agents |
| `openai` | An OpenAI-compatible endpoint — OpenAI, Gemini's compatibility endpoint, DeepSeek, OpenRouter, most gateways. | Required | both agents |
| `ollama` | A local Ollama. **Internal-only**: it projects into no agent whatever its scope says, because there is no key to write. | None | nothing |
| `unknown` | A probe was inconclusive. Coffer hides nothing — it starts open and you decide. | Required | both agents |

Supply exactly one of `--secret` (stored encrypted under `provider/<name>/key`, only the ref is kept) or `--credential-ref` (reuse a vault entry you already have). Both, or neither, is rejected — except for `ollama`, which must supply neither.

```bash
coffer provider list            # name · protocol · base URL · active · internal
coffer provider list --json
coffer provider show my-gateway
coffer provider edit my-gateway --base-url https://gateway.internal/v1
coffer provider edit my-gateway --secret "<new-key>"   # rotate; the ref stays
coffer provider rm my-gateway
```

The credential ref is not editable — it is the vault address this connection owns. The protocol is, because the probe that guessed the wire can be wrong and correcting it in place beats deleting the connection and re-entering the key: `coffer provider edit <name> --protocol <wire>`. That one edit is refused while the connection is **active**, because the wire decides whether it covers any agent at all and which wire `use-builtin` reverts — so changing it live could leave a projection behind that nothing would ever take off. Put the agents back on their own login first (`coffer provider use-builtin <wire>`), edit, then switch again. Renaming is its own operation — it moves the vault entry, the row and any live projection together — and lives on the connection's detail page or at `POST /api/v1/providers/{name}/rename`.

## Which agents it reaches

Reach is not a field on the connection. It is the framework's per-agent **scope**, the same control every scoped kind uses:

```bash
coffer scope show provider:my-gateway
coffer scope set provider:my-gateway --agents claude_code
coffer scope set provider:my-gateway --no-agents      # dormant: reaches nothing
```

That is how an OpenAI-compatible gateway is pointed at **Claude Code**: the projection writer is chosen by the **agent type**, not by the protocol, so a connection reaching `claude_code` writes Claude's `settings.json` in the anthropic shape whatever its own wire says. Coffer translates nothing between protocols — the endpoint really has to speak what the agent sends.

The resource's `enabled` switch narrows the projection and only the projection: a disabled connection writes into nothing and resolves no key, while the reach you configured is still reported, so switching a connection off never looks like it erased the agent list. Scope, like every reach in Coffer, is a per-machine decision and does not travel between machines.

## Switch an agent onto it

```bash
coffer provider switch my-gateway
```

```
switched to my-gateway [openai] → claude-code
```

The switch projects first and flips activation second, so a native-config write that fails aborts the switch with the registry unchanged. It takes over every agent its scope reaches from whichever connection held them, de-projecting that one from the agents the new one does not cover: **at most one active connection per agent type**. A connection reaching an agent type you have not registered here is recorded active and reports that type as `skipped` — not an error. The whole thing is audited as `provider_switched` with `{from, to, protocol, agents}`.

What lands in the file is only Coffer's own keys, merged into what is already there:

| Agent | File | Keys Coffer owns |
| --- | --- | --- |
| Claude Code | `~/.claude/settings.json` | `apiKeyHelper`, `env.ANTHROPIC_BASE_URL`, and — from the agent's binding — `env.ANTHROPIC_MODEL`, `env.ANTHROPIC_SMALL_FAST_MODEL` |
| Codex | `~/.codex/config.toml` | `model`, `model_provider = "coffer"`, and `[model_providers.coffer]` with `name`, `base_url`, `wire_api`, `env_key` |

`ANTHROPIC_API_KEY` is never written — it would override the helper. Everything outside the managed keys is preserved, comments and ordering included, and the write is atomic with a backup: the previous contents become `<file>.bak`, the old `.bak` rotating to `.bak.1` and then `.bak.2`.

A write carries the fingerprint of the text it read. If you or the agent's own CLI saved that file in between, the write is **refused** with `409 CONFIG_FILE_STALE` and audited as `provider_projection_refused` — your edit stays on disk and the caller re-reads and retries.

When the connection curates a model set, a Codex projection is two files: `config.toml` plus a Coffer-owned `coffer-model-catalog.json` beside it, with `model_catalog_json` pointing at it, so Codex's **own** picker lists the endpoint's models instead of OpenAI's. That key replaces Codex's built-in list rather than adding to it, which is why an uncurated connection writes no catalogue at all. De-projection drops the pointer and retires the file — and only ever a file under Coffer's own name.

## Back to the built-in login

```bash
coffer provider use-builtin anthropic
```

```
anthropic back on its built-in login, was my-anthropic → claude-code
```

`use-builtin` is `switch`'s other half: it strips Coffer's keys from the native config of the agent behind that wire — `anthropic` → Claude Code, `openai` → Codex — and clears the active connection, so the agent goes back to whatever login it had before. It is idempotent: run it when nothing is active and it succeeds having done nothing. A connection reaching several agents reverts as a unit, because the single active flag is all-or-nothing.

De-projection is ownership-aware in both directions. An `apiKeyHelper` is removed only when it is one Coffer wrote; Codex's `model_provider` and top-level `model` are cleared only while `model_provider` still points at Coffer. A helper or a provider block you chose yourself is left exactly where it is.

## The key never leaves the vault

The raw key stays Fernet-encrypted in the credential store and is materialised on demand. It is never written into `settings.json`, `config.toml`, or any other file Coffer touches.

- **Claude Code** gets a helper command: `apiKeyHelper = "coffer provider key --connection <name>"`. The helper names the **connection**, not the wire, so a projected agent always fetches exactly the key of the connection that was activated.
- **Codex** gets `env_key = "COFFER_PROVIDER_KEY"`. Coffer fills that variable for any Codex process it spawns itself; a Codex you start in your own shell needs it exported there — the accepted cost of credential isolation, since Codex offers no helper-command seam:

```bash
export COFFER_PROVIDER_KEY="$(coffer provider key --connection my-gateway)"
```

`coffer provider key --wire <wire>` is the legacy form, kept for `settings.json` files written before helpers named connections; it resolves whichever connection is active for that wire's agent. Either way the raw value goes to stdout and is never logged.

## What a connection offers

A gateway account often serves dozens of models when its owner uses two. `models` is that answer — the **offered** set, not a chosen model — and every picker downstream respects it. Empty, the default, means no restriction: everything the endpoint serves.

Each entry is `{id, modality}`, where the modality is `text`, `embedding`, `image`, `video` or `audio`, because one endpoint answers for more than chat. Every chat picker narrows to `text`, so an embedding model can never be bound as the model an agent runs on. Ids stay opaque: Coffer validates their shape and passes them to the vendor verbatim, so an id the endpoint stops serving is a stale menu entry rather than a config error.

Curating is done on the connection's **Models** tab, or over `PATCH /api/v1/providers/{name}`, whose `models` field replaces the whole set (`null` leaves it alone, `[]` clears the restriction).

## Coffer's own engine

At most one connection, globally, is the endpoint Coffer's own passes run on:

```bash
coffer provider internal-default local-ollama
```

```
internal engine now uses local-ollama [ollama]
```

Setting it clears the flag from any previous holder and audits `provider_internal_default_set`. It is what the knowledge tidy pass, memory aggregation and organise, the machine-merge attempt on a [sync](/guide/sync) conflict, and voice transcription for channel audio all run on. With nothing marked, each of those is a clean no-op rather than an error.

The **model** those passes use is a separate global setting — `GET`/`PUT /api/v1/internal-engine-config`, or **Settings → Engine** in the app, alongside each pass's own switch and interval. A connection may be both active for your agents and the internal default at once: one key, two uses.

## When the flag and the file disagree

`is_active` is a row in Coffer's database; what it *means* is a few keys in a file Coffer does not own, which the agent's own CLI, other tooling, a restore from backup and you all rewrite. At boot Coffer checks, for each agent type with an active connection reaching it, whether the projection is actually in that agent's config — and when it is not, **clears the flag**, so every surface then says the agent is on its built-in login.

It heals in one direction only. It never writes the projection back: a flag left over from an earlier session is no warrant to re-route your agent through a gateway you are not currently using. Run `coffer provider switch <name>` again if you did want it. The reverse drift — Coffer's keys present while the registry says inactive — is reported, never silently removed.

## The pages and REST

**Model providers**, at `/model-providers` in the sidebar's RESOURCES group, is the library: a table of name, vendor (derived from the base URL by matching it against the presets — OpenAI, Anthropic, Google Gemini, DeepSeek, OpenRouter, Ollama, or Custom), base URL and reach, with Add in the header and Delete per row. There is deliberately **no per-row switch**: activation is per agent, and it lives on the agent.

A connection's own page has **Overview** and **Models** tabs, with the shared reach control in its header. The Models tab introspects the endpoint as it opens — which models an endpoint serves is a fact about the endpoint, like an MCP server's tool list — says so while it works, and offers a retry if the probe fails; a failed or empty probe leaves your selection alone.

The switch itself is on the **agent** detail page's Overview tab, filtered to the connections that reach that agent. Picking a connection or a model there is a **draft**: it stages a choice, makes you test it against the endpoint, and only the confirm step patches the binding and activates the connection. On the built-in login the panel offers no model control at all — only a line saying where the model is chosen instead.

Over HTTP the connections live under `/api/v1/providers` — the collection, `{name}`, `{name}/activate`, `use-builtin/{wire}`, `{name}/rename`, `{name}/internal-default`, `{name}/key` and the legacy `active-key/{wire}`. Endpoint introspection is `POST /api/v1/models/list-models`, `/test-connection` and `/detect-protocol`, each accepting an inline secret so a connection can be tested before it is saved. Reach is the framework's own surface, `GET`/`PUT /api/v1/resources/provider/{name}/scope`.

[Skills →](/guide/skills)
