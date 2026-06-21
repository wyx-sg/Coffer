# Quickstart — Coffer Provider Switching

Manage LLM provider profiles centrally in Coffer, then switch the matching
agent's native config atomically.

## Prerequisites

- Coffer's daemon is running (start the desktop app or `coffer daemon`).
- At least one agent is registered (auto-detected or via `coffer agent add` —
  see spec 004 quickstart).

## Add a provider profile

Supply the raw API key with `--secret` (or omit it to be prompted):

```bash
# Anthropic provider (projects to Claude Code)
coffer provider add my-anthropic \
  --wire anthropic \
  --base-url https://api.anthropic.com \
  --model claude-opus-4-5 \
  --fast-model claude-haiku-4-5 \
  --secret sk-ant-...

# OpenAI-compatible provider (projects to Codex)
coffer provider add my-openai \
  --wire openai \
  --base-url https://api.openai.com \
  --model gpt-4o \
  --wire-api chat \
  --secret sk-...
```

Coffer:
1. Validates the profile fields.
2. Stores the raw key in the Fernet vault under `provider/<name>/key`.
3. Persists a Resource of kind `provider` (config holds only `credential_ref`,
   never the raw key).
4. Audits `RESOURCE_CREATED`.

## Reuse an existing credential ref

If you already have a credential stored (e.g., shared across two profiles):

```bash
coffer provider add my-alternate \
  --wire anthropic \
  --base-url https://api.anthropic.com \
  --model claude-sonnet-4-6 \
  --credential-ref provider/my-anthropic/key
```

## Activate (switch) a provider

```bash
coffer provider switch my-anthropic
```

Coffer:
1. Sets `my-anthropic` as the active anthropic profile (clears any previous
   one, then sets the target — serialised by the single-process daemon).
2. Projects into `~/.claude/settings.json` — merging these managed keys:
   - `apiKeyHelper = "coffer provider key --wire anthropic"`
   - `env.ANTHROPIC_BASE_URL = <base_url>`
   - `env.ANTHROPIC_MODEL = <model>`
   - `env.ANTHROPIC_SMALL_FAST_MODEL = <fast_model>` (omitted if not set)
3. Creates `~/.claude/settings.json.bak` before writing.
4. Preserves ALL other keys in `settings.json` (theme, mcpServers, …) unchanged.
5. Reports which agents were updated and which were skipped.
6. Audits `PROVIDER_SWITCHED`.

## Claude Code — no extra steps needed

Because `apiKeyHelper = "coffer provider key --wire anthropic"` is written into
`settings.json`, Claude Code calls that command to fetch the key on demand.
**No environment variable is needed for Claude Code.** The raw key is never
written to disk.

## Codex — set the env var in your shell

Because Codex reads the key from `COFFER_PROVIDER_KEY`, you must export it in
your shell before starting Codex:

```bash
export COFFER_PROVIDER_KEY="$(coffer provider key --wire openai)"
codex  # or however you launch it
```

Or add it to your shell's init file (`~/.zshrc`, `~/.bashrc`):

```bash
# Dynamically resolves the active openai provider key on shell start
export COFFER_PROVIDER_KEY="$(coffer provider key --wire openai 2>/dev/null || true)"
```

> **Why is this step needed for Codex?**
> This is the accepted consequence of Decision B (credential isolation): the raw
> key is never written to `config.toml`. Codex reads from an env var
> (`env_key = "COFFER_PROVIDER_KEY"` in `~/.codex/config.toml`). Auto-injection
> of this env var into Coffer-spawned Codex processes is deferred to the
> hot-switch PR.

## List and inspect profiles

```bash
coffer provider list
coffer provider list --json | jq '.providers[].name'
coffer provider show my-anthropic
```

## Resolve the active key (apiKeyHelper)

Claude Code calls this automatically, but you can also call it directly:

```bash
coffer provider key --wire anthropic   # active anthropic profile
coffer provider key --wire openai      # active openai profile
```

Resolution is by active profile for the given wire format. There is no
`<name>` positional form for this subcommand.

The raw key is printed to stdout only. It is not logged.

## Update a profile

```bash
# Change model or base URL
coffer provider edit my-anthropic --model claude-opus-4-5-20251101

# Rotate the stored key
coffer provider edit my-anthropic --secret sk-ant-newkey...
```

Updating a key rotates the Fernet vault entry; `credential_ref` stays the same.

## Remove a profile

```bash
coffer provider remove my-anthropic
```

If no other profile shares the credential ref, the vault entry is deleted.

## Desktop app

Open Coffer → **Providers** in the sidebar. The Providers page shows a table
of all profiles with columns: name, wire format, base URL, model, active.

Row actions:
- **Switch** — activates the profile (same as `coffer provider switch`)
- **Delete** — removes the profile (with confirmation)

To edit a profile (change model, base URL, or rotate the key), use the CLI
(`coffer provider edit`) or the PATCH API. There is no inline edit on the page.

The **Add** button opens a form to create a new profile. The raw key is
accepted only in this form dialog and is immediately stored in the vault.

## How the on-disk layout looks

```
~/.coffer/sync/
  resources/
    provider/
      my-anthropic.yaml    # synced profile config (no secret)
  credentials/
    provider/
      my-anthropic/
        key.enc            # Fernet ciphertext of the raw API key

~/.claude/settings.json    # managed keys merged (apiKeyHelper, env.*)
~/.claude/settings.json.bak   # backup created before each projection

~/.codex/config.toml       # managed keys merged (model, model_providers.coffer.*)
~/.codex/config.toml.bak      # backup created before each projection
```

## Troubleshooting

**"Neither secret_value nor credential_ref provided"** — pass `--secret` (or be
prompted) or pass `--credential-ref` to reuse an existing vault entry.

**"Both secret_value and credential_ref provided"** — supply exactly one. Use
`--credential-ref` to reuse an existing key instead of supplying a new one.

**"No active anthropic profile found"** — run `coffer provider switch <name>`
to activate one before using `coffer provider key`.

**Codex does not pick up the new provider** — make sure you exported
`COFFER_PROVIDER_KEY` in the current shell session after the switch
(`export COFFER_PROVIDER_KEY="$(coffer provider key --wire openai)"`). A
running Codex process will not pick up changes until it is restarted with the
updated env var.

**"settings.json contains unexpected keys after switch"** — Coffer only merges
the defined managed keys and never removes others. If you see unexpected changes,
check `~/.claude/settings.json.bak` (the backup before the last switch) and
compare.

**Activating a profile reports `skipped: ["codex"]`** — no Codex agent is
registered in Coffer yet. Register one with `coffer agent add` (see spec 004)
or the desktop Agents page. The profile is still marked active.
