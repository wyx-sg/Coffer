# Quickstart — Coffer Provider Switching

Register an LLM connection once — an endpoint plus a key — then point an agent
at it. Coffer writes the agent's own native config file and keeps the raw key in
its encrypted vault.

A connection is an **optional override**. An agent with no connection projected
runs on its own built-in login, so nothing here is a prerequisite for using an
agent through Coffer.

## Prerequisites

- Coffer's daemon is running (`coffer daemon start`, or `coffer open`, which
  starts it and opens the web UI).
- At least one agent is registered (auto-detected, or `coffer agent add` — see
  spec agent-registry).

## Add a connection

`--protocol` says which wire the endpoint speaks; it is what drives model
introspection and whether a key is required. Supply exactly one of `--secret`
(stored encrypted) or `--credential-ref` (reuse a vault entry you already have).

```bash
# An Anthropic-wire endpoint
coffer provider add my-anthropic \
  --protocol anthropic \
  --base-url https://api.anthropic.com \
  --secret sk-ant-...

# An OpenAI-compatible gateway
coffer provider add my-openai \
  --protocol openai \
  --base-url https://api.openai.com/v1 \
  --secret sk-...

# An ollama endpoint — internal-engine only, and it has no key
coffer provider add local-ollama \
  --protocol ollama \
  --base-url http://127.0.0.1:11434
```

Coffer:

1. Validates the connection's shape.
2. Stores the raw key in the Fernet vault under `provider/<name>/key` and keeps
   only the ref.
3. Persists a resource of kind `provider` whose config holds the protocol, the
   base URL, the credential ref and the curated model set — never the key, and
   never a model it runs.
4. Gives the connection the scope its wire starts with: both coding agents for a
   credentialed wire, no agent at all for `ollama`.
5. Audits `resource_created`.

No model is chosen here. The model is picked where it is used — the per-agent
binding, the internal-engine selector, or the conversation.

## Reuse an existing credential

```bash
coffer provider add my-alternate \
  --protocol anthropic \
  --base-url https://api.anthropic.com \
  --credential-ref provider/my-anthropic/key
```

The vault entry stays owned by the connection that created it; deleting
`my-alternate` leaves it alone while another connection cites it.

## Route a connection to the agents you want

Which agents a connection projects into is the resource's per-agent scope, the
same surface every scoped kind uses. This is how an OpenAI-compatible gateway
is pointed at Claude Code:

```bash
coffer scope show provider:my-openai
coffer scope set provider:my-openai --agents claude_code
```

`--no-agents` makes the connection dormant — it reaches nothing. Scope is a
per-machine decision and does not travel between machines.

## Switch an agent onto a connection

```bash
coffer provider switch my-anthropic
```

Coffer:

1. Takes over every agent the connection reaches, clearing `is_active` on the
   connection that held those agents before and de-projecting it from any agent
   the new one does not cover (at most one active connection per agent type).
2. Projects into each reached agent's native config, merging only Coffer-managed
   keys, through an atomic write that leaves a `.bak`. A concurrent edit to that
   file is refused rather than overwritten.
3. Reports the agents written (`projected`) and those it reaches but that are
   not registered here (`skipped`) — skipping is not an error.
4. Audits `provider_switched`.

Claude Code gets `apiKeyHelper`, `env.ANTHROPIC_BASE_URL`, and — from the
agent's binding — `env.ANTHROPIC_MODEL` / `env.ANTHROPIC_SMALL_FAST_MODEL`.
Codex gets `model`, `model_provider = "coffer"` and a
`[model_providers.coffer]` block, plus a Coffer-owned model catalogue file when
the connection curates models.

The model comes from the agent's binding, not from the connection, so bind one
before you switch (the web Agent page's Overview tab stages a connection + model
draft, makes you test it, and only then confirms). Over HTTP:

```bash
curl -X PATCH "$COFFER_URL/api/v1/agents/<agent-name>" \
  -H "X-Coffer-Token: $COFFER_TOKEN" \
  -d '{"model": "claude-opus-4-6", "fast_model": "claude-haiku-4-5"}'
```

## Back to the built-in login

```bash
curl -X POST "$COFFER_URL/api/v1/providers/use-builtin/anthropic" \
  -H "X-Coffer-Token: $COFFER_TOKEN"
```

Coffer removes the keys it owns from that agent's native config and clears the
active connection's flag. A connection reaching several agents reverts as a
unit.

## Claude Code — nothing else to do

`apiKeyHelper = "coffer provider key --connection <name>"` is written into
`settings.json`, so Claude Code fetches the key on demand from exactly the
connection that was activated. No environment variable, and the raw key never
lands on disk.

## Codex — the key reaches it through an env var

`[model_providers.coffer].env_key = "COFFER_PROVIDER_KEY"`, and Codex reads the
key from that variable. When Coffer spawns Codex itself (a chat conversation or
a channel turn), it materialises the key into that variable for the child
process. For a Codex you start yourself in a shell, export it first:

```bash
export COFFER_PROVIDER_KEY="$(coffer provider key --connection my-openai)"
codex
```

> **Why the extra step for a standalone Codex?**
> Codex has no `apiKeyHelper` equivalent, and writing the raw key into
> `config.toml` would break credential isolation. An env var is the only seam
> Codex offers, and only a process Coffer spawns can be handed one.

## Curate which models a connection offers

A gateway account often serves dozens of models when its owner uses two. The
curated set on the connection is that answer, and every downstream picker
respects it:

```bash
coffer provider show my-openai   # .models is the curated set
```

Each entry is `{id, modality}`, where the modality is `text`, `embedding`,
`image`, `video` or `audio`. An EMPTY set means no restriction — everything the
endpoint serves. Chat pickers take the `text` entries only, so an embedding
model can never be picked as an agent's chat model. Curation is done on the
connection's detail page (Models tab) or over `PATCH /api/v1/providers/{name}`,
whose `models` field replaces the whole set.

## Coffer's own engine

One connection — at most one, globally — is the endpoint Coffer's internal
passes run on:

```bash
coffer provider internal-default local-ollama
```

The model those passes use is a separate global setting
(`PUT /api/v1/internal-engine-config`), not a field on the connection; changing
the connection drops a model the new one does not curate rather than aiming
Coffer at a model that endpoint never heard of. With no connection marked, the
internal passes are a clean no-op.

## List and inspect

```bash
coffer provider list
coffer provider list --json | jq '.providers[].name'
coffer provider show my-anthropic
```

## Print a key

```bash
coffer provider key --connection my-anthropic   # what Coffer projects
coffer provider key --wire anthropic            # legacy: whichever connection
                                                # is active for that wire's agent
```

The raw key goes to stdout only, and is never logged.

## Update a connection

```bash
# Change the endpoint
coffer provider edit my-anthropic --base-url https://gateway.example.com

# Rotate the stored key (the ref stays the same)
coffer provider edit my-anthropic --secret sk-ant-newkey...
```

`credential_ref` is immutable. Renaming is its own operation — it moves the
vault entry, the audit trail and any live projection together — and is available
on the detail page or over `POST /api/v1/providers/{name}/rename`.

## Remove a connection

```bash
coffer provider rm my-anthropic
```

If no other resource cites the credential ref, the vault entry goes with it.

## Web UI

**Model providers** in the sidebar's RESOURCES group is the connection library:
a table of name, vendor (derived from the base URL), base URL and reach, with
Add in the header and Delete per row. There is no per-row switch — activation is
per agent and lives on the Agent detail page's Overview tab.

A connection's own page has an Overview tab and a Models tab. The Models tab
introspects the endpoint when it opens, says so while it is working, and offers a
retry if the probe fails; each row carries the model's id, its type and whether
it is offered. The header's scope control is where the connection is enabled,
disabled or re-targeted.

## How the on-disk layout looks

```
~/.coffer/sync/
  resources/
    provider/
      my-anthropic.yaml    # the connection's config (no secret)
  credentials/
    provider/
      my-anthropic/
        key.enc            # Fernet ciphertext of the raw API key

~/.claude/settings.json          # Coffer-managed keys merged in
~/.claude/settings.json.bak      # backup before the last projection
                                 # (.bak.1 / .bak.2 hold the two before it)

~/.codex/config.toml             # Coffer-managed keys merged in
~/.codex/config.toml.bak         # same three-generation rotation
~/.codex/coffer-model-catalog.json   # written when the connection curates models
```

## Troubleshooting

**"invalid provider config"** — for an `anthropic` / `openai` / `unknown` wire
supply exactly one of `--secret` / `--credential-ref`; for `ollama` supply
neither.

**`no active provider for wire …`** — nothing is active for that wire's agent.
Use `coffer provider key --connection <name>`, or switch a connection first.

**The agent still runs on its built-in login** — Coffer clears `is_active` at
boot when the agent's native config no longer carries its projection: something
else rewrote that file. It never re-projects on its own; run
`coffer provider switch <name>` again.

**Claude Code rejects every model** — the connection is routed to Claude Code but
the agent's binding names a model that endpoint does not serve. Bind a model the
endpoint actually returns (curate the connection's models, then pick one), and
test before confirming.

**Codex will not start** — `wire_api` accepts only `responses`; Codex refuses to
load a `config.toml` that says anything else.

**`skipped: ["codex"]` after a switch** — the connection reaches Codex but no
Codex agent is registered here. Register one (`coffer agent add`, or the web
Agents page). The connection is still active.

**`settings.json` has keys you did not expect** — Coffer merges only its managed
keys and removes nothing else. Compare against
`~/.claude/settings.json.bak`, the copy taken before the last projection.
