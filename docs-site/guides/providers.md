---
title: Model providers
description: Store a model endpoint and its key once, switch Claude Code or Codex onto it, curate its models, see what requests through it cost, and choose the model Coffer's own engine runs on.
---

# Model providers

A model provider is a credentialed endpoint — a base URL, a protocol and one encrypted API key — that Coffer can write into your agents' own configuration and also use for its own work. This page covers adding providers, choosing which agents they reach, switching an agent onto one and back, curating the models they offer, reading what requests through them cost, and pointing Coffer's internal engine at one.

## What providers are for

Claude Code reads its endpoint from `settings.json`; Codex reads its from `config.toml`. Moving an agent to a different gateway by hand means editing each file, pasting keys in plain text, and keeping no record of what changed. With a provider in Coffer you:

- store the endpoint and key once, encrypted;
- switch an agent onto it in one action, and back to the agent's own login in another;
- keep every switch in the audit log;
- reuse the same key for Coffer's own engine.

A provider is always optional. An agent with no provider switched on runs on its own built-in login, and every Coffer surface still works.

## The Model providers page

**Model providers** is one page with one header — the title, an **Experimental** tag, a line saying what the page is for, and **Add provider** — over two tabs, **Providers** and **Usage**. The header and its **Add provider** button are the same on both tabs. This section is the **Providers** tab, one list beside one provider; the **Usage** tab, `/model-providers?tab=usage`, is described in [Usage](/guides/usage).

- **The list** (left) has a **Filter** and one row per provider: a drag handle, its mark, its name, its protocol and what it offers ("9 models", "All models", or "Coffer's engine only" for an Ollama-protocol provider), and the marks of the agents running on it. It is headed **Fallback order**, with a help tip: **the order is fallback priority** (see [Failover](#failover-between-providers)). Drag a row, or focus its handle and press ↑ / ↓, to move it. A chip marks the provider Coffer's own engine uses (**Coffer · background model**) and the one that transcribes speech (**Coffer · speech to text**); both are changed in **Settings › General**. Opening the page opens the first provider.
- **The header** of the open provider shows its health, read from listing the endpoint's models when you open it — **Reachable**, **Key rejected** or **Unreachable** — its protocol, host and, when the endpoint answered, how long it took, the **Reach** control, **Test**, **Edit**, and a **⋯** menu with **Delete provider**.
- **The detail** is one column, with no tabs: **Used by**, **Endpoint** and **Models**. A problem shows only in the header's pill and in the section it belongs to — an unreachable endpoint or a rejected key in **Endpoint**, a failed listing in **Models** — never again on each **Used by** row. **Used by** lists each agent running on the provider with its model, as a link reading **Codex › Change model** that opens that agent's page with its Change model form already open (see [Change an agent's model](/guides/agents#change-an-agent-s-model)), and **Coffer's engine** and **Speech to text** when the provider carries them, which open **Settings › General**. The list is read-only. **Endpoint** shows the protocol (locked while an agent runs on the provider), the runtime for a local one, the base URL, the **Route** (agents reach it through Coffer's proxy, `127.0.0.1:38471`), the API key as the secret it is stored under — never the key itself — with **Replace key** and a link to **Secrets**, and **Fallback**: the switch **Use as a fallback** (a local runtime is never a fallback). **Models** is the curated list with each model's price (see [below](#curate-the-models-a-provider-offers)).

The provider's address is `/model-providers/<uid>`.

With no provider yet, the page offers three ways in — **Anthropic or compatible**, **OpenAI or compatible**, **A local runtime on this Mac** — shows what each agent runs on right now (its own login), and says when Coffer's own model is not set.

## Add a provider

Open **Model providers** and click **Add provider**. The dialog has two steps.

1. **Endpoint.** Pick a **Vendor** from the grid — **Anthropic**, **OpenAI**, **Google Gemini**, **DeepSeek**, **OpenRouter**, **Ollama**, **LM Studio** — which fills in the protocol and base URL, or **Custom** for a gateway or relay, which asks for the protocol by what can use it: **OpenAI-compatible** (Codex, chat and Coffer's engine) or **Anthropic-compatible** (Claude Code, chat and Coffer's engine). Give it a **Name** and paste the **API key**; the key becomes a new secret in this Mac's keychain-encrypted store and is never shown again. **Test** lists the endpoint's models with the key you typed — "Connected in 180 ms", or "The endpoint rejected the key (401)" — and nothing is saved until you add the provider. Missing or malformed fields are named under each field.
2. **Models.** Tick the models the provider should offer, with search and a type filter. Nothing ticked means every model the endpoint serves is offered. **Add provider** saves it and opens it.

Choosing **Ollama** or **LM Studio** takes the local path instead: no key, and Coffer looks for a runtime on this Mac (see [Local model runtimes](#local-model-runtimes)). The next step stays greyed out until a runtime is chosen or an address is filled in, and the **Name** field appears once a runtime is chosen.

| Protocol | Meaning | Key |
| --- | --- | --- |
| `anthropic` | Anthropic Messages API | required |
| `openai` | OpenAI-compatible API (OpenAI, Gemini's OpenAI endpoint, DeepSeek, OpenRouter, most gateways) | required |
| `ollama` | a local Ollama server; used only by Coffer's own engine, never projected into an agent | none |
| `unknown` | the endpoint's protocol could not be determined | required |

The protocol describes the endpoint. It decides how Coffer lists the endpoint's models and whether a key is needed; it does not decide which agent the provider is written into — that is the provider's reach.

## Choose which agents a provider reaches

A new provider with a key reaches every agent, including agents you register later. An `ollama` provider starts dormant and never reaches an agent.

Use the **Reach** control in the provider's header on **Model providers**.

The file Coffer writes is chosen by the **agent**, not by the protocol. Reaching `claude-code` writes Claude Code's `settings.json` in its shape; reaching `codex` writes Codex's `config.toml`. That is how an OpenAI-compatible gateway can drive Claude Code — as long as the gateway really accepts what Claude Code sends. Coffer does not translate between protocols.

## Switch an agent onto a provider

### From the agent page

1. Open **Agents**, choose the agent, and under **Model** on its **Overview** click **Change…**. (From a provider's **Used by** list, **Codex › Change model** opens the same form.)
2. Pick a **Provider**. Only enabled providers that reach this agent are offered, beside the agent's built-in login.
3. Pick a **Model**; for Claude Code also the **Model per tier**. The first model the endpoint returns is pre-selected, and the tiers are prefilled with suggestions.
4. Click **Review changes**. Coffer lists, file by file, the lines it will write — `settings.json` for Claude Code; `config.toml` and Coffer's model list file for Codex — and tests the provider with the chosen model while it does. A failed test is a warning, not a block.
5. Click **Apply**. Coffer writes the files and records the model and the provider on the agent in one step. If a file changed after the review was drawn, nothing is written and the review offers **Reload preview**.

Picking the **Built-in login** puts the agent back on its own login; the form asks for nothing else. The details of the form are in [Change an agent's model](/guides/agents#change-an-agent-s-model).

The agent's **Overview › Model** section then reads the provider, the model and the **Route** — through Coffer's proxy, with a **Test** button. **Rotate proxy token**, which replaces the agent's own local token for Coffer's proxy, is in the agent page's **⋯** menu, offered only while the agent runs on a provider; the built-in login bypasses the proxy.

Which provider an agent runs on is a field of the agent itself (its `connection_uid`), so an agent is on at most one provider at a time and the choice stays on this machine; it never syncs. A provider that is deleted, switched off or no longer reaches the agent leaves that agent on its own login.

Which provider an agent runs on is a setting of the agent itself, so an agent is on at most one provider and switching one agent never moves another. Switching an agent onto a provider it is not reached by (the provider is switched off, or the provider's reach does not name the agent) is refused with `PROVIDER_DOES_NOT_REACH_AGENT`. The choice is per machine: it is part of the agent's record, which is not synced.

The model lives on the **agent**, not on the provider: a provider says which gateway account to use, and the agent's binding says which model to run there. An agent with no model bound gets no model key written and runs on its own default.

## What gets written

An agent on a provider does not call the provider directly. It calls Coffer's **local model proxy** on `127.0.0.1:38471`, which forwards each request to the provider with the real key attached, fails over to another provider serving the same model if the first one fails before answering, and records what the request cost ([Usage](/guides/usage)). How the proxy works is in [The local model proxy](/architecture/model-proxy). What lands in the agent's own file is therefore the proxy's address and a command that prints the agent's own **local proxy token** — never the provider's endpoint or its key.

Coffer merges only its own keys into the agent's file and leaves everything else as it was. Writes go through the same machinery as the [config-file editor](/guides/agents#edit-config-files): atomic, with `.bak`, `.bak.1` and `.bak.2` kept, and refused with `CONFIG_FILE_STALE` if the file changed after Coffer read it (audited as `provider_projection_refused`).

### Claude Code — `<config_dir>/settings.json`

```json
{
  "apiKeyHelper": "/Users/you/.coffer/bin/coffer proxy token --agent-uid 3f1c0b9a7d2e4c5f8a6b1d0e9f2c3a4b",
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:38471/anthropic",
    "NO_PROXY": "127.0.0.1,localhost",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-pro",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-pro",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-pro"
  },
  "model": "deepseek-pro",
  "modelPicker": {
    "options": [{ "model": "deepseek-pro", "label": "deepseek-pro", "description": "via Coffer" }],
    "replaceBuiltInOptions": true
  }
}
```

- **The key is never written.** Claude Code runs `apiKeyHelper`, and `coffer proxy token --agent-uid <uid>` prints the agent's local token, which unlocks only the loopback proxy. The proxy swaps it for the provider's key. `ANTHROPIC_API_KEY` is never written, because it would override the helper. For an agent this machine does not have, the helper prints nothing and exits with code 4.
- **The file names the proxy, not the provider.** Switching Claude Code from one API-key provider to another changes the proxy's route; `settings.json` stays as it is, and renaming a provider touches nothing.
- **`NO_PROXY`** gains `127.0.0.1,localhost`, so a corporate `HTTPS_PROXY` never captures the loopback call. Your own entries stay, and switching back removes only the pair Coffer appended.
- **The model** goes in the top-level `model` key, which `/model` also saves to, so choosing another model inside Claude Code sticks. Coffer writes no effort key: the agent runs at the effort its own configuration names, and an `effortLevel` an earlier version wrote stays in your file as your own setting.
- **Every tier is pinned.** Claude Code asks for models by tier — Opus, Sonnet, Haiku (which also runs its background tasks) and Fable. On an endpoint that serves no Claude ids each tier is the agent's model; on a gateway serving Claude ids each tier is the model whose name carries it. **Model per tier** in the Change model dialog sets one yourself.
- **`modelPicker`** puts the provider's models in `/model`, replacing the built-in rows when the provider serves no Claude ids.

The helper names the `coffer` CLI by absolute path (shell-quoted if the path holds a space), because Claude Code started from the Dock or Finder does not get your login shell's `PATH`. For an install under `~/.coffer/bin` the path is the stable `~/.coffer/bin/coffer`, so an upgrade does not break it.

### Codex — `<config_dir>/config.toml`

```toml
model = "deepseek-flash"
model_provider = "coffer"
model_catalog_json = "/Users/you/.codex/coffer-model-catalog.json"

[model_providers.coffer]
name = "Coffer (deepseek)"
base_url = "http://127.0.0.1:38471/openai/v1"
wire_api = "responses"
supports_websockets = false
requires_openai_auth = false
auth = { command = "/Users/you/.coffer/bin/coffer", args = ["proxy", "token", "--agent-uid", "8e2d…"], timeout_ms = 30000 }
```

The file is edited with `tomlkit`, so your comments and key order survive. Codex runs the `auth` command for its token itself, so a Codex you start in your own terminal needs nothing exported (`timeout_ms` raises Codex's 5 second default so a cold start is not cut off), and no key is in any Codex process's environment. The command-backed `auth` table needs **Codex 0.155.1 or later**. `supports_websockets = false` keeps Codex from trying the Responses WebSocket transport first, which stalls against any base URL but OpenAI's.

When the provider curates models, Coffer writes its own catalogue next to `config.toml` so Codex's picker lists them. Each entry carries the model's context window, and an auto-compact limit at 90% of it, from what the provider records for the model. Coffer writes no `model_reasoning_effort`; one an earlier version wrote stays in your file as your own setting.

Reverting to the built-in login removes exactly the keys Coffer wrote. A `model` you changed since with `/model` is yours and stays, and so is any effort key an earlier version wrote.

## Local model runtimes

A provider can be a model runtime on this machine: **Ollama** (≥ 0.14.0 for Claude Code, ≥ 0.13.4 for Codex), **LM Studio** (≥ 0.4.1 / ≥ 0.3.29), **vLLM** (≥ 0.11.1 / ≥ 0.10.0) or llama.cpp's **llama-server** (Codex support is experimental). Coffer talks to each in its own native protocol through the proxy — no translation — so `mlx_lm.server`, which speaks only Chat Completions, is not supported; use LM Studio's MLX engine.

In **Add provider**, choose **Ollama** or **LM Studio**. Coffer looks on each runtime's default port (or at the loopback address you type, then **Detect**) and lists what answered — the runtime, its version, the protocols it serves and its models. Pick one and the protocol to use: **Anthropic-compatible** or **OpenAI-compatible** when the runtime serves it, or **Ollama API** for Coffer's engine only. The next step starts with the models that can call tools ticked, each showing its context window.

If nothing answers, the dialog says so and offers a prompt for your agent (**Ask an agent**, with **Copy prompt** in its menu) to set a runtime up on this machine: it names the machine, the runtimes and default ports Coffer probes, and the versions that serve both agents' protocols, prefers Ollama or LM Studio, and asks for one tool-calling model that fits your memory. Press **Detect** once it is running. Installing a runtime yourself works just as well — start it on its default port, or type the address of one that is already running.

- **Detection is read-only.** It probes loopback addresses only (each runtime's default port, or the URL you give), fingerprints the runtime rather than trusting the port, and never pulls, loads or downloads a model. vLLM's default port 8000 is shared by many development servers, so it is not probed by default: type vLLM's address, then press **Detect**.
- **A local runtime needs no key**; Coffer curates the runtime's models that can call tools, each with the context window the runtime serves it with. Ollama's served window is known once the model is loaded; before that it is unknown, and Coffer then writes no window for the model rather than guessing one.
- **Claude Code** gets `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` (local runtimes reject its beta fields) and `CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to the served window, with every tier pinned to the one model. **Codex** gets the window in its catalogue. Coffer never runs Codex with `--oss`, which can pull models.
- Agents work far better with a window of at least 64k tokens; token counts from local runtimes are approximate, and a first request may wait for a cold model load.

## Curate the models a provider offers

A gateway account often serves dozens of models when you use two or three. The provider's curated list says which ones Coffer offers downstream.

1. Open **Model providers** and choose the provider.
2. Scroll to **Models**. Coffer lists the endpoint's models when the provider opens, and says when it last did; **Refresh**, beside the section's title, asks again. If listing fails, the title reads **Listing failed · last listed &lt;date&gt;**, a box says what failed, and **Refresh** is the way to try again; your current selection is left alone and still offered. An endpoint that lists nothing says so: leave it like that and every model the endpoint accepts stays available.
3. Switch on the models to offer, and correct each one's **Type** if the guess is wrong — it reads as plain text with a chevron and opens a menu: **Text / chat**, **Embedding**, **Image**, **Video** or **Audio**. A search and a **Type** filter narrow the list; a model Coffer's engine, speech to text or an agent uses carries a tag saying so. **Turn all on** and **Turn all off**, beside the search, switch every model the search and filter match in one step; turning all off is refused while it would leave no model on, because an empty list means every model is offered.

Only switched-on models appear in agent, chat and channel pickers, and chat pickers list text models only. (The section's help tip says so too.)

### Model prices

The line under the **Models** title says once where most prices come from — "bundled with Coffer, updated &lt;date&gt;", or from the provider — and each model row shows its price per 1M tokens (input · output), marking only the exceptions:

- **You set** — a price you recorded on this provider; it wins over everything else. **Set price…** (or click the price) opens a small form with the input and output price and, at the bottom left, **Reset to default**, which removes it.
- **From `<provider>`** — the provider's own API reported it when its models were listed (OpenRouter does). It is refreshed each time the models are listed or refreshed, never per request.
- **Bundled · updated `<date>`** — Coffer's price list: pydantic's genai-prices, with Coffer's own Anthropic rates for the newest models. It knows prices per provider, historical prices and long-context tiers. A copy ships with each release, and the daemon refreshes it from genai-prices once a day; the date is when the data in use was taken. **Refresh model prices** in **Settings › General** turns the refresh off on a firewalled machine. No price is ever looked up while a request is being costed.
- **Local · no cost** — a model runtime on this Mac.
- **—** — nothing prices it, with **Set price…**. [Usage](/guides/usage) shows `—` for it until you set one.

An empty selection means no restriction: every model the endpoint serves. Model ids are passed to the vendor verbatim and never checked against a list inside Coffer.

What a model picker offers for an agent is decided in one place and served to every surface — the Conversations page, and a channel's `/model` card:

- when the provider the agent runs on curates **text** models, exactly those, in your order;
- otherwise, the agent's own catalogue (see [Agents](/guides/agents#models)).

Non-text models are never offered as chat models. A provider that curates only non-text models offers no chat model at all. Reading this list never touches the network.

## Failover between providers

When an agent's model is offered by more than one enabled provider, Coffer's proxy moves a request that fails before its first byte (a connection error, a 5xx, 529 or 429, a rejected key, or a first-byte timeout) to the next provider that offers the same model. It is automatic and needs no setup:

- The providers are tried in the **order of the Model providers list**, the agent's own provider first. Drag the rows to change it.
- **Use as a fallback** (on by default, in the provider's **Endpoint**) decides whether other providers' requests may fail over to it.
- A local runtime never fails over and is never a fallback.
- The model never changes, and nothing fails over after the first byte of the answer; the agent's own retry lands on a healthy provider.
- Each failover is recorded in **Activity**, and **Usage** meters the provider that actually answered.

See [The local model proxy](../architecture/model-proxy.md#failover) for the exact rules.

## Edit, rename and delete

On the provider's header:

- **Edit** changes the **Name**, the **Protocol** and the **Base URL**, with **Test** before you save. Renaming changes only the label; the page stays where it is. The protocol is locked while an agent runs on the provider. The key is not edited here.
- **Replace key** (on Overview, or the key-rejected banner) takes a new key, can **Test** it first, and overwrites the value behind the same secret — the agents' config files only name the secret, so they do not change. The new value takes effect at once. See [Secret store](/guides/secret-store).
- **⋯ › Delete provider** deletes a provider nothing runs on, with its secret, after a confirmation. A provider something runs on is not blocked: **Delete provider** opens a review instead. The left side says what will happen to each user — an agent goes back to its own login, Coffer's engine pauses, speech to text turns off, the key is deleted — and the right side shows exactly the lines Coffer will remove from each agent's config file (for Codex its model, provider table and model-list pointer; your own lines stay). **Delete** applies it: the agents are put back on their own logins first, then the provider goes. If an agent's file changed in the meantime the delete stops with the provider still there.

- **Replacing** the key overwrites the stored secret at the same ref; nothing that cites it changes.
- **Waiting for approval.** A new base URL for a connection whose key already goes somewhere, and a key another connection already uses, are saved but held until you approve them in the Coffer app. The old URL stays in use until then; a replaced key is not held.
- **Changing the protocol** is refused with `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` while an agent runs on the provider. Put each agent running on it (the refusal names them) back on its **Built-in login**, edit, then switch again.
- **Renaming** changes only the label. The uid, the secret ref and the agents' files stay as they are; Codex's `name = "Coffer (<name>)"` label updates on the next switch.
- **Deleting** first puts every agent that runs on the provider back on its own login, then removes the provider and deletes its secret if nothing else cites it.

## Boot self-check

The agent's recorded provider is a fact about a file Coffer does not own: the agent's CLI, other tools, you, or a restore from backup can all rewrite it. At every daemon start, Coffer checks each agent that runs on a provider. If the agent's config no longer carries Coffer's keys, Coffer clears that agent's provider, so every surface shows it on its built-in login. It does **not** write the projection back: a choice left over from an earlier session is no reason to re-route your agent through a gateway you may have stopped using. If the reverse is true — Coffer's keys are in the file while the agent runs on no provider — Coffer leaves the file alone.

After a [vault sync](/guides/vault-sync) round brings in provider changes from another machine, Coffer re-projects every agent that runs on a provider on this machine from the provider as it now is. A switch made on another machine does not arrive: which provider an agent runs on, like reach, is per machine and never synced.

## Coffer's own engine

Some of Coffer's work runs on a model of its own: memory organisation, knowledge curation, and voice transcription for channels. That model borrows the endpoint and key of one provider and names its own model. With nothing configured, knowledge curation and memory distillation fall back to a mechanical pass (see [Knowledge](/guides/knowledge#without-an-internal-model) and [Memory](/guides/memory#how-the-passes-run)), and a voice message reaches the agent as an audio file.

**Web UI:** open **Settings › General** and find the **Coffer's model** section. It has two pickers, and each one is a provider first and then a model from that provider's list:

- **Coffer's engine** distils agents' memory and curates knowledge. It lists the provider's chat models. Under it, **Time limit per call** bounds one call to the model; the default option names the number it stands for.
- **Speech to text** transcribes voice messages that arrive through channels. It lists the provider's speech models, and **Off — do not transcribe** clears the model. It is a separate provider on purpose: a chat gateway often has no transcription endpoint, so the two are set independently and neither falls back to the other.

A choice saves as soon as you make it; there is no Save button. A line under each picker says where it stands:

- **Not set** — a provider or a model is missing. For the engine, no internal pass runs and distil and curation wait; for speech to text, voice messages reach the agent as audio files, without a transcript.
- **Set** — both halves are chosen and have not been tested during this visit.
- **Answering** or **Failing** — the result of **Test**. For the engine, Test sends one small chat request to the chosen provider and model. For speech to text, a chat request would fail on a speech model, so Test instead asks the provider which models it serves: it passes when the list names your model and fails when it does not. A provider that answers but lists no models reads **Reachable**, because the model can't be checked. A failure shows the reason on that line and changes nothing: the pair stays as you chose it until you pick another one.

The passes Coffer runs on its own are switched on the pages they upkeep: curation from the **Automatic** control in the Knowledge header, reading and distilling memory from the one in the Memory header.

At most one provider is the internal-engine default, and at most one carries speech to text; setting either moves the flag from wherever it was. A provider can be switched into agents and be the engine's default at the same time. An `ollama` provider can only ever serve the engine. When the engine's provider changes, the engine model is cleared unless the new provider's curated list includes it.

The unattended passes, the per-call time limit and which machine may run knowledge curation are Settings page controls as well. The engine provider and the speech-to-text provider have no default: move the flag by choosing another provider. `coffer daemon status` shows the passes running right now.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Switch fails with `CONFIG_FILE_STALE` | The agent's config changed between Coffer's read and write | Run the switch again. |
| Switch fails with `PROVIDER_DOES_NOT_REACH_AGENT` | The provider is switched off, or the provider's reach does not name the agent | Switch it on or add the agent to its reach, then switch again. |
| Switch fails with `PROVIDER_INTERNAL_ONLY` | You tried to switch an agent onto an `ollama` provider | Use it as the internal-engine default instead. |
| The agent gets `503` "no connection is active" from the proxy | The provider the agent runs on was disabled, no longer reaches the agent, or its key is missing | Check the provider's reach and key. |
| The agent gets `401` from the proxy | The helper printed no token, or a stale one | Run the `apiKeyHelper` / `auth` command from the agent's file yourself; **Rotate proxy token** in the agent page's **⋯** menu issues a fresh one. |
| Nothing answers on `127.0.0.1:38471` | The proxy is not running | The daemon restarts a crashed proxy within a few seconds; `coffer daemon status` shows whether the daemon is up. |
| The agent page shows the built-in login | Coffer's regular check found the agent's config no longer carries the projection, and cleared the agent's provider rather than re-route it | Switch again if you still want the provider. |

## Related

- [Agents](/guides/agents) — model binding and the agent's own catalogue
- [Usage](/guides/usage) — what requests through your providers cost, the Usage tab of this page
- [Secret store](/guides/secret-store) — where provider keys are stored
- [Conversations](/guides/chat) and [Channels](/guides/channels) — where models are picked per conversation
- [LLM Connections Are Projected Into Each Agent's Own Config File](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/provider-connections-projected-into-agent-config.md)
- Specs: [provider-switching](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/provider-switching/spec.md), [internal-engine](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/internal-engine/spec.md)
