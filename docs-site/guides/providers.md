---
title: Model providers
description: Store a model endpoint and its key once, switch Claude Code or Codex onto it, curate its models, and choose the model Coffer's own engine runs on.
---

# Model providers

A model provider is a credentialed endpoint — a base URL, a protocol and one encrypted API key — that Coffer can write into your agents' own configuration and also use for its own work. This page covers adding providers, choosing which agents they reach, switching an agent onto one and back, curating the models they offer, and pointing Coffer's internal engine at one.

## What providers are for

Claude Code reads its endpoint from `settings.json`; Codex reads its from `config.toml`. Moving an agent to a different gateway by hand means editing each file, pasting keys in plain text, and keeping no record of what changed. With a provider in Coffer you:

- store the endpoint and key once, encrypted;
- switch an agent onto it in one action, and back to the agent's own login in another;
- keep every switch in the audit log;
- reuse the same key for Coffer's own engine.

A provider is always optional. An agent with no provider switched on runs on its own built-in login, and every Coffer surface still works.

## Add a provider

**Web UI:** open **Model providers** and click **Add model provider**. Pick a preset — **OpenAI**, **Anthropic**, **Google Gemini**, **DeepSeek**, **OpenRouter**, **Ollama** — which fills in the base URL and protocol, or **Custom** to enter both yourself. Paste the **API key**; the dialog can test the connection and list the endpoint's models before you save.

**CLI:**

```sh
# Store the key first, so it never appears on a command line
printf '%s' "$DEEPSEEK_API_KEY" | coffer credentials set deepseek/key

coffer provider add deepseek \
  --protocol openai \
  --base-url https://api.deepseek.com \
  --credential-ref deepseek/key
# added provider deepseek (openai)
```

`coffer provider add` also accepts `--secret <key>`, which stores the key under a new opaque ref of the form `provider/<uuid>/key` — but the value then sits in your shell history. For `anthropic`, `openai` and `unknown` you must give exactly one of `--secret` or `--credential-ref`.

| Protocol | Meaning | Key |
| --- | --- | --- |
| `anthropic` | Anthropic Messages API | required |
| `openai` | OpenAI-compatible API (OpenAI, Gemini's OpenAI endpoint, DeepSeek, OpenRouter, most gateways) | required |
| `ollama` | a local Ollama server; used only by Coffer's own engine, never projected into an agent | none |
| `unknown` | the endpoint's protocol could not be determined | required |

The protocol describes the endpoint. It decides how Coffer lists the endpoint's models and whether a key is needed; it does not decide which agent the provider is written into — that is the provider's reach.

## Choose which agents a provider reaches

A new provider with a key reaches every agent, including agents you register later. An `ollama` provider starts dormant and never reaches an agent.

**Web UI:** use the **Reach** control on the provider's row, or in its page header.

**CLI:**

```sh
coffer scope set provider deepseek --agents codex
coffer scope show provider deepseek
coffer scope clear provider deepseek
```

The file Coffer writes is chosen by the **agent**, not by the protocol. Reaching `claude-code` writes Claude Code's `settings.json` in its shape; reaching `codex` writes Codex's `config.toml`. That is how an OpenAI-compatible gateway can drive Claude Code — as long as the gateway really accepts what Claude Code sends. Coffer does not translate between protocols.

## Switch an agent onto a provider

### From the agent page

1. Open **Agents**, choose the agent, and stay on **Overview**.
2. In the **Model provider** card, pick a **Provider**. Only enabled providers that reach this agent are offered.
3. Pick a **Model** (and, for Claude Code, a **Fast model**). The first model the endpoint returns is pre-selected.
4. Click **Test connection**. **Confirm switch** stays disabled until the test passes for the current provider and model.
5. Click **Confirm switch**. Coffer saves the model on the agent and then activates the provider — the only step that writes the agent's config.

Picking **Use built-in (agent's own login)** and confirming puts the agent back on its own login; no test is needed.

### From the command line

```sh
coffer agent edit claude-code --model sonnet --fast-model haiku
coffer provider switch deepseek
# switched to deepseek [openai] → claude_code, codex

coffer provider use-builtin anthropic   # Claude Code back on its own login
coffer provider use-builtin openai      # Codex back on its own login
```

`use-builtin` takes the wire of the agent to revert: `anthropic` for Claude Code, `openai` for Codex. It is idempotent. Because a provider's active flag covers every agent it was switched into, reverting one wire reverts the provider as a unit.

At most one provider is active per agent type. Switching to a new one takes the agents it reaches over from the previous one and removes the previous projection from any agent the new one does not cover. If no agent the provider reaches is registered, the switch still marks it active and reports the skipped types.

The model lives on the **agent**, not on the provider: a provider says which gateway account to use, and the agent's binding says which model to run there. An agent with no model bound gets no model key written and runs on its own default.

## What gets written

Coffer merges only its own keys into the agent's file and leaves everything else as it was. Writes go through the same machinery as the [config-file editor](/guides/agents#edit-config-files): atomic, with `.bak`, `.bak.1` and `.bak.2` kept, and refused with `CONFIG_FILE_STALE` if the file changed after Coffer read it (audited as `provider_projection_refused`).

### Claude Code — `<config_dir>/settings.json`

```json
{
  "apiKeyHelper": "/Users/you/.coffer/bin/coffer provider key --connection-uid 59ecb631d06a501c936fa5affdace553",
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com",
    "ANTHROPIC_MODEL": "sonnet",
    "ANTHROPIC_SMALL_FAST_MODEL": "haiku"
  }
}
```

The key is never written. Claude Code runs the `apiKeyHelper` command to fetch it, and `coffer provider key --connection-uid <uid>` prints the decrypted key for exactly that provider. The helper cites the provider's uid, so renaming the provider does not break it. `ANTHROPIC_API_KEY` is never written, because it would override the helper. When the provider is disabled or no longer reaches any agent, the helper prints nothing and exits with code 4, so Claude Code does not keep a stale key.

The helper names the `coffer` CLI by absolute path (shell-quoted if the path holds a space), because Claude Code started from the Dock or Finder does not get your login shell's `PATH`. For an install under `~/.coffer/bin` the path is the stable `~/.coffer/bin/coffer`, not the versioned directory behind it, so an upgrade does not break it. The path is resolved at each switch.

::: warning When no CLI is found
If the daemon cannot find the `coffer` CLI when it writes the projection, it writes the bare `coffer provider key …` instead, which works only where `coffer` is on the `PATH` Claude Code runs with. Switch again after installing the CLI to get the absolute form.
:::

### Codex — `<config_dir>/config.toml`

```toml
model = "deepseek-flash"
model_provider = "coffer"
model_catalog_json = "/Users/you/.codex/coffer-model-catalog.json"

[model_providers.coffer]
name = "Coffer (deepseek)"
base_url = "https://api.deepseek.com"
wire_api = "responses"
env_key = "COFFER_PROVIDER_KEY"
```

The file is edited with `tomlkit`, so your comments and key order survive. Codex reads the key from the `COFFER_PROVIDER_KEY` environment variable. Coffer sets it for every Codex process it starts itself ([chat](/guides/chat) and [channel](/guides/channels) turns). For Codex runs you start in your own shell, export it there:

```sh
export COFFER_PROVIDER_KEY="$(coffer provider key --connection-uid 59ecb631d06a501c936fa5affdace553)"
```

`model_catalog_json` and the `coffer-model-catalog.json` file beside `config.toml` are written only when the provider curates text models; they replace Codex's built-in model list with the ones the endpoint serves. Switching back removes both and Codex's own list returns.

Reverting to the built-in login removes exactly these keys — and removes `apiKeyHelper` only when it is Coffer's own.

## Curate the models a provider offers

A gateway account often serves dozens of models when you use two or three. The provider's curated list says which ones Coffer offers downstream.

1. Open **Model providers** and choose the provider.
2. Open **Models**. Coffer lists the endpoint's models as soon as the tab opens (**Listing this endpoint's models…**). If listing fails, the tab says so and offers **Retry**; your current selection is left alone.
3. Turn on the models to offer, and correct each one's **Type** if the guess is wrong: **Text / chat**, **Embedding**, **Image**, **Video** or **Audio**.

An empty selection means no restriction: every model the endpoint serves. Model ids are passed to the vendor verbatim and never checked against a list inside Coffer.

What a model picker offers for an agent is decided in one place and served to every surface — the Chat page, a channel's `/model` card, and `coffer agent models`:

- when the agent's active provider curates **text** models, exactly those, in your order;
- otherwise, the agent's own catalogue (see [Agents](/guides/agents#models)).

Non-text models are never offered as chat models. A provider that curates only non-text models offers no chat model at all. Reading this list never touches the network.

## Edit, rename and delete

```sh
coffer provider edit deepseek --base-url https://api.deepseek.com/v1
coffer provider edit deepseek --secret "$NEW_KEY"      # rotates the key in place
coffer resource rename provider deepseek deepseek-eu
coffer provider rm deepseek
```

- **Rotating** the key overwrites the stored secret at the same ref; nothing that cites it changes.
- **Changing the protocol** is refused with `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` while the provider is switched on. Run `coffer provider use-builtin <wire>`, edit, then switch again.
- **Renaming** changes only the label. The uid, the credential ref and the projected `apiKeyHelper` stay as they are; Codex's `name = "Coffer (<name>)"` label updates on the next switch.
- **Deleting** removes the provider and deletes its credential if nothing else cites it.

## Boot self-check

The active flag records a fact about a file Coffer does not own: the agent's CLI, other tools, you, or a restore from backup can all rewrite it. At every daemon start, Coffer checks each active provider against the agents it reaches. If an agent's config no longer carries Coffer's keys, Coffer clears the active flag, so every surface shows that agent on its built-in login. It does **not** write the projection back: a flag left over from an earlier session is no reason to re-route your agent through a gateway you may have stopped using. If the reverse is true — Coffer's keys are in the file while nothing is marked active — Coffer leaves the file alone.

After a [vault sync](/guides/vault-sync) round brings in provider changes from another machine, Coffer re-derives the projection on this machine: for each agent type with a registered agent, it projects the active provider that reaches it, or removes Coffer's keys if none does. Reach itself is per machine and never synced.

## Coffer's own engine

Some of Coffer's work runs on a model of its own: memory organisation, knowledge curation, sync conflict resolution, and voice transcription for channels. That model borrows the endpoint and key of one provider and names its own model. With nothing configured, knowledge curation and memory distillation fall back to a mechanical pass (see [Knowledge](/guides/knowledge#without-an-internal-model) and [Memory](/guides/memory#how-the-passes-run)), a sync conflict waits for you to resolve it, and a voice message reaches the agent as an audio file.

**Web UI:** open **Settings → Coffer's model**. The **Coffer's model** card picks the **Model provider** and **Model**, plus the **Time limit per call**. The **Speech to text** card picks a separate **Transcription provider** and **Transcription model**; a chat gateway often has no transcription endpoint, so the two are set independently and neither falls back to the other.

**CLI:**

```sh
coffer provider internal-default deepseek      # the endpoint and key
coffer engine model set deepseek-flash         # the model
coffer engine model show

coffer provider transcribe-default openai-direct
coffer engine transcribe-model set whisper-1
```

At most one provider is the internal-engine default, and at most one carries speech to text; setting either moves the flag from wherever it was. A provider can be switched into agents and be the engine's default at the same time. An `ollama` provider can only ever serve the engine. When the engine's provider changes, the engine model is cleared unless the new provider's curated list includes it.

`coffer engine` also controls the unattended passes (`coffer engine upkeep list|set|runs`), the per-call time limit (`coffer engine timeout`), and which machine may run knowledge curation (`coffer engine curate-owner`). See the [CLI reference](/reference/cli).

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Switch fails with `CONFIG_FILE_STALE` | The agent's config changed between Coffer's read and write | Run the switch again. |
| Switch fails with `PROVIDER_INTERNAL_ONLY` | You tried to switch an agent onto an `ollama` provider | Use it as the internal-engine default instead. |
| Claude Code sends requests without a key | The provider was disabled or reaches no agent, or the helper runs a bare `coffer` that is not on the `PATH` Claude Code runs with | Run the `apiKeyHelper` command from `settings.json` yourself; switch again to rewrite it with the CLI's absolute path. |
| Codex run from your shell fails to authenticate | `COFFER_PROVIDER_KEY` is not exported there | Export it as shown above. |
| The agent page shows the built-in login after a restart | The boot self-check found the agent's config no longer carries the projection | Switch again if you still want the provider. |
| A `wire_api` other than `responses` is refused | Codex refuses to load any other value | Leave it at `responses`. |

## Related

- [Agents](/guides/agents) — model binding and the agent's own catalogue
- [Credentials](/guides/credentials) — where provider keys are stored
- [Chat](/guides/chat) and [Channels](/guides/channels) — where models are picked per conversation
- [LLM Connections Are Projected Into Each Agent's Own Config File](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/provider-connections-projected-into-agent-config.md)
- Specs: [provider-switching](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/provider-switching/spec.md), [internal-engine](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/internal-engine/spec.md)
