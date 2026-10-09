---
title: Model providers
description: Store a model endpoint and its key once, switch Claude Code or Codex onto it, curate its models, see what requests through it cost, and choose the model Coffer transcribes voice messages with.
---

# Model providers

A model provider is a credentialed endpoint — one or two addresses and one encrypted API key — that Coffer can write into your agents' own configuration and also use for its own work. This page covers adding providers, which agents can use them, switching an agent onto one and back, curating the models they offer, reading what requests through them cost, and pointing Coffer's speech-to-text at one.

## What providers are for

Claude Code reads its endpoint from `settings.json`; Codex reads its from `config.toml`. Moving an agent to a different gateway by hand means editing each file, pasting keys in plain text, and keeping no record of what changed. With a provider in Coffer you:

- store the endpoint and key once, encrypted;
- switch an agent onto it in one action, and back to the agent's own login in another;
- keep every switch in the audit log;
- reuse the same key for Coffer's speech-to-text.

A provider is always optional. An agent with no provider switched on runs on its own built-in login, and every Coffer surface still works.

## The Model providers page

<Shot name="providers" alt="The Model providers page." />

**Model providers** is one page with one header — the title, a line saying what the page is for, and **Add provider** — over two tabs, **Providers** and **Usage**. The header and its **Add provider** button are the same on both tabs. This section is the **Providers** tab, one list beside one provider; the **Usage** tab, `/model-providers?tab=usage`, is described in [Usage](/guides/usage).

- **The list** (left) has a **Filter** and one row per provider, sorted by name: its mark, its name, its protocol and what it offers ("9 models" or "All models"), and the marks of the agents running on it. A provider whose endpoint does not answer or refuses its key says so on its row in red — **Unreachable** or **Key rejected** in place of protocol and models — whether or not you have opened it (see [Health](#health)). A chip marks the provider that transcribes speech (**Coffer · speech to text**); it is changed in **Settings › General**. Opening the page opens the first provider.
- **The header** of the open provider shows its health, read from listing the endpoint's models when you open it — **Reachable**, **Key rejected** or **Unreachable** — which agents can use it ("For Claude Code, Codex"), its host and, when the endpoint answered, how long it took, **Test**, **Edit**, and a **⋯** menu with **Delete provider**.
- **The detail** is one column, with no tabs: **Used by**, **Endpoint** and **Models**. A problem shows only in the header's pill and in the section it belongs to — an unreachable endpoint or a rejected key in **Endpoint**, a failed listing in **Models** — never again on each **Used by** row. **Used by** lists each agent running on the provider with its model, as a link reading **Codex › Change model** that opens that agent's page with its Change model form already open (see [Change an agent's model](/guides/agents#change-an-agent-s-model)), and **Speech to text** when the provider carries it, which opens **Settings › General**. The list is read-only. **Endpoint** shows the provider's addresses, each saying which agent uses it (the runtime and its address for a local one), the **Route** (agents reach it through Coffer's proxy, `127.0.0.1:38471`), the API key as the secret it is stored under — never the key itself — with **Replace key** and a link to **Secrets**. **Models** is the curated list with each model's price (see [below](#curate-the-models-a-provider-offers)).

The provider's address is `/model-providers/<uid>`.

With no provider yet, the page offers three ways in — **Anthropic or compatible**, **OpenAI or compatible**, **A runtime on this Mac** — each opening **Add provider** with that kind chosen.


### Health

Coffer keeps each provider's health itself, so a broken one shows before you open it:

- **Checked on its own.** Coffer lists every switched-on provider's models when the daemon starts and every 30 minutes after, and again right after you edit a provider — a replaced key or a corrected URL clears its error without waiting. Listing models spends no tokens. A provider whose key is waiting for your approval is not called until you approve it.
- **Learned from your agents.** When an agent's request through Coffer is refused with 401 or 403, or never reaches the endpoint, the provider is marked at once; a request that is answered marks it working again. A rate limit or a server error says nothing about the provider and changes nothing.
- **Shown in the list and on Overview.** The list marks each failing row. **Needs you** on [Overview](/guides/web-ui#overview) lists a failing provider an agent runs on, or that speech to text uses: **Check** tries an unreachable one again right in the row, **Replace key** opens a rejected one's page. A provider nothing uses is marked only in the list, since a local runtime you have not started is not a problem.

## Add a provider

Open **Model providers** and click **Add provider**. The dialog has two steps.

<Shot name="add-provider-dialog" alt="The Add provider dialog." />

1. **Endpoint.** Pick a **Vendor** from the grid, or **Custom** for a gateway or relay. A vendor fills in its addresses:
   - the **OpenAI-compatible address**, which Codex uses;
   - the **Anthropic-compatible address**, which Claude Code uses, where the vendor has one.

   **DeepSeek**, for example, fills `https://api.deepseek.com` and `https://api.deepseek.com/anthropic`, so one provider serves both agents. **Custom** shows both fields empty: fill in what your gateway serves, or the same address in both if it serves both at one address. A vendor whose mainland-China addresses differ (**Kimi**, **Zhipu GLM**, **MiniMax**, **Qwen**, **SiliconFlow**) also asks for the **Region**, because a key works only in the region it was created in. Give it a **Name** and, under **API key**, pick a secret Coffer already holds or paste a new key; a pasted key becomes a new secret in this Mac's keychain-encrypted store and is never shown again. **Test** lists the endpoint's models with that key — "Connected in 180 ms", or "The endpoint rejected the key (401)" — and nothing is saved until you add the provider. A stored key is sent only to the endpoint of the connection that holds it, so testing one against a new endpoint reads "Not tested: this stored key can't go to this endpoint yet" and sends nothing: paste the key to test it, or add the provider, approve its key for the endpoint, and test it from the provider's page. Missing or malformed fields are named under each field.
2. **Models.** Tick the models the provider should offer, with search and a type filter. Nothing ticked means every model the endpoint serves is offered. **Add provider** saves it and opens it.

Choosing **Ollama** or **LM Studio** takes the local path instead: no key, and Coffer looks for a runtime on this Mac (see [Local model runtimes](#local-model-runtimes)). The next step stays greyed out until a runtime is detected, and the **Name** field appears once a runtime is chosen.

The vendors:

- Anthropic, OpenAI and Google Gemini
- DeepSeek, OpenRouter, xAI, Mistral, Groq, Together AI and Fireworks AI
- Kimi, Zhipu GLM, MiniMax, Qwen, SiliconFlow, Baidu Qianfan, Tencent Hunyuan and StepFun
- Ollama and LM Studio (local runtimes)

Each preset's addresses are the ones its vendor documents. A vendor that documents no Anthropic-compatible address (OpenAI, Gemini, Mistral, Groq, Together AI) can't be used from Claude Code, because Coffer doesn't translate between the two APIs. Put a translating gateway such as LiteLLM in front of it and add that as **Custom**.

Coffer stores the addresses as a protocol plus one or two URLs:

| Protocol | Stored when | Key |
| --- | --- | --- |
| `openai` | there is an OpenAI-compatible address; an Anthropic-compatible one is kept beside it | required |
| `anthropic` | there is only an Anthropic-compatible address | required |
| `unknown` | the endpoint's protocol could not be determined; it is tried on both | required |

A provider saved before the `ollama` protocol was retired keeps that value: it stays in the list and can be deleted, but it reaches no agent, and no provider can be created on it or edited onto it. Add a local Ollama runtime on its Anthropic or OpenAI protocol instead (see [Local model runtimes](#local-model-runtimes)).

## Which agents can use a provider

A provider serves the agents it has an address for:

- Claude Code speaks the Anthropic API, so it needs an Anthropic-compatible address.
- Codex speaks the OpenAI API, so it needs an OpenAI-compatible address.

The provider's header says which ("For Claude Code, Codex"), and an agent's **Change model** form offers only the providers that serve it. There is nothing else to set: a provider has no reach control and no on/off switch. Which provider an agent runs on is the agent's own choice. A provider you no longer want is deleted.

Coffer's proxy sends Claude Code's requests to the Anthropic-compatible address and Codex's to the OpenAI-compatible one, unchanged. Coffer does not translate between protocols.

Providers saved by an earlier version are brought in line when Coffer starts:

- An agent on a provider that was switched off goes back to its own login, and the provider's reach settings are cleared.
- An OpenAI-compatible provider Claude Code was running on gets its own address as its Anthropic-compatible address, so Claude Code keeps working.
- A DeepSeek provider Codex isn't running on gets `https://api.deepseek.com/anthropic`. Its key then waits for your approval for that address, like any new address.

## Switch an agent onto a provider

### From the agent page

1. Open **Agents**, choose the agent, and under **Model** on its **Overview** click **Change…**. (From a provider's **Used by** list, **Codex › Change model** opens the same form.)
2. Pick a **Provider**. Only providers that serve this agent are offered, beside the agent's built-in login.
3. Pick a **Model**; for Claude Code also the **Model per tier**. The first model the endpoint returns is pre-selected, and the tiers are prefilled with suggestions.
4. Wait for the line under **Model**: Coffer tests the provider with the chosen model by itself, and it reads **Connection OK** with how long it took, or **Connection failed** with the reason and **Retry**. **Review changes** stays off until the test passes; the built-in login needs none.
5. Click **Review changes**. Coffer lists, file by file, the lines it will write — `settings.json` for Claude Code; `config.toml` and Coffer's model list file for Codex.
6. Click **Apply**. Coffer writes the files and records the model and the provider on the agent in one step. If a file changed after the review was drawn, nothing is written and the review offers **Reload preview**. After a successful apply a notice says the change takes effect once you restart that agent; sessions already open keep the old setting.

Picking the **Built-in login** puts the agent back on its own login; the form then asks only for its **Model** — the agent's own default, or one of its own models. The details of the form are in [Change an agent's model](/guides/agents#change-an-agent-s-model).

**Built-in default** names the model it runs on when the agent itself reports it, as in **Built-in default (GPT-5 Codex)**: Codex marks its default model. Claude Code picks its default from your account at each turn and nothing on your machine records it, so with no model in its own config it reads plain **Built-in default**.

Switching Claude Code changes the Claude Code CLI only. The Claude desktop app reads its model routing from its own third-party inference settings, not from `settings.json`, so it keeps its own model.

The agent's **Overview › Model** section then reads the provider, the model and the **Route** — through Coffer's proxy, with a **Test** button. **Rotate proxy token**, which replaces the agent's own local token for Coffer's proxy, is in the agent page's **⋯** menu, offered only while the agent runs on a provider; the built-in login bypasses the proxy.

Which provider an agent runs on is a field of the agent itself (its `connection_uid`), so an agent is on at most one provider at a time and the choice stays on this machine; it never syncs. A provider that is deleted, or no longer has an address for the agent, leaves that agent on its own login.

Which provider an agent runs on is a setting of the agent itself, so an agent is on at most one provider and switching one agent never moves another. Switching an agent onto a provider with no address for it is refused with `PROVIDER_DOES_NOT_REACH_AGENT`. The choice is per machine: it is part of the agent's record, which is not synced.

The model lives on the **agent**, not on the provider: a provider says which gateway account to use, and the agent's binding says which model to run there. An agent with no model bound gets no model key written and runs on its own default.

## What gets written

An agent on a provider does not call the provider directly. It calls Coffer's **local model proxy** on `127.0.0.1:38471`, which forwards each request to the provider with the real key attached, fails over to another provider serving the same model if the first one fails before answering, and records what the request cost ([Usage](/guides/usage)). How the proxy works is in [The local model proxy](/architecture/model-proxy). What lands in the agent's own file is therefore the proxy's address and a command that prints the agent's own **local proxy token** — never the provider's endpoint or its key.

Coffer merges only its own keys into the agent's file and leaves everything else as it was. Writes go through the same machinery as the [writes Coffer makes to an agent's config](/guides/agents#what-coffer-reads-and-what-it-writes): atomic, with the previous version copied to `~/.coffer/config-backups`, and refused with `CONFIG_FILE_STALE` if the file changed after Coffer read it (audited as `provider_projection_refused`).

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
- **Every tier is pinned.** Claude Code asks for models by tier — Opus, Sonnet, Haiku (which also runs its background tasks) and Fable, which is pinned only when the provider curates a model carrying that name. On an endpoint that serves no Claude ids each tier is the agent's model; on a gateway serving Claude ids each tier is the model whose name carries it. **Model per tier** in the Change model dialog sets one yourself.
- **`modelPicker`** puts the provider's models in `/model`, replacing the built-in rows when the provider serves no Claude ids.
- **`CLAUDE_CODE_MAX_CONTEXT_TOKENS`** is the agent's model's context window, when the model is not a Claude model and its window is known (see [Context windows](#context-windows)). Claude Code otherwise assumes 200k tokens for a model it does not know, warns that it "isn't described by this version's model catalog", and compacts there. The value holds for the session: a model you pick later with `/model` keeps it until Coffer switches the agent again.

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

When the provider curates models, Coffer writes its own catalogue next to `config.toml` so Codex's picker lists them. Each entry carries the model's context window, and an auto-compact limit at 90% of it, where the model's window is known (see [Context windows](#context-windows)). Coffer writes no `model_reasoning_effort`; one an earlier version wrote stays in your file as your own setting.

Reverting to the built-in login removes exactly the keys Coffer wrote. The form there also sets the agent's own `model` (or clears it to the built-in default), and a `model` you changed since with `/model` is yours and stays, and so is any effort key an earlier version wrote.

## Local model runtimes

A provider can be a model runtime on this machine: **Ollama** (≥ 0.14.0 for Claude Code, ≥ 0.13.4 for Codex), **LM Studio** (≥ 0.4.1 / ≥ 0.3.29), **vLLM** (≥ 0.11.1 / ≥ 0.10.0) or llama.cpp's **llama-server** (Codex support is experimental). Coffer talks to each in its own native protocol through the proxy — no translation — so `mlx_lm.server`, which speaks only Chat Completions, is not supported; use LM Studio's MLX engine.

In **Add provider**, choose **Ollama** or **LM Studio**. Coffer looks on each runtime's default port (or at the loopback address you type, then **Detect again**) and lists what answered — the runtime, its version, the protocols it serves and its models. Pick one and the protocol to use: **Anthropic-compatible** or **OpenAI-compatible**, whichever the runtime serves. The next step starts with the models that can call tools ticked, each showing its context window.

If nothing answers, the dialog says so and offers a prompt for your agent (**Hand off to &lt;Agent&gt;**, with **Copy prompt** in its menu) to set a runtime up on this machine: it names the machine, the runtimes and default ports Coffer probes, and the versions that serve both agents' protocols, prefers Ollama or LM Studio, and asks for one tool-calling model that fits your memory. Press **Detect again** once it is running. Installing a runtime yourself works just as well — start it on its default port, or type the address of one that is already running.

- **Detection is read-only.** It probes loopback addresses only (each runtime's default port, or the URL you give), fingerprints the runtime rather than trusting the port, and never pulls, loads or downloads a model. vLLM's default port 8000 is shared by many development servers, so it is not probed by default: type vLLM's address, then press **Detect again**.
- **A local runtime needs no key**; Coffer curates the runtime's models that can call tools, each with the context window the runtime serves it with. Ollama's served window is known once the model is loaded; before that it is unknown, and Coffer then writes no window for the model rather than guessing one.
- **Claude Code** gets `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` (local runtimes reject its beta fields) and `CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to the served window, with every tier pinned to the one model. **Codex** gets the window in its catalogue. Coffer never runs Codex with `--oss`, which can pull models.
- Agents work far better with a window of at least 64k tokens; token counts from local runtimes are approximate, and a first request may wait for a cold model load.

## Curate the models a provider offers

A gateway account often serves dozens of models when you use two or three. The provider's curated list says which ones Coffer offers downstream.

1. Open **Model providers** and choose the provider.
2. Scroll to **Models**. Coffer lists the endpoint's models when the provider opens, and says when it last did; **Refresh**, beside the section's title, asks again. If listing fails, the title reads **Listing failed · last listed &lt;date&gt;**, a box says what failed, and **Refresh** is the way to try again; your current selection is left alone and still offered. An endpoint that lists nothing says so: leave it like that and every model the endpoint accepts stays available.
3. Switch on the models to offer, and correct each one's **Type** if the guess is wrong — it reads as plain text with a chevron and opens a menu: **Text / chat**, **Embedding**, **Image**, **Video** or **Audio**. A search and a **Type** filter narrow the list; a model speech to text or an agent uses carries a tag saying so. The list is a table — Model, Price, Window, Type — and rows can be ticked (the header box ticks every model the search and filter show): a selection bar then replaces the search with **Turn on** and **Turn off** for the ticked models.

Only switched-on models appear in agent, chat and channel pickers, and chat pickers list text models only. (The section's help tip says so too.)

### Model prices

The line under the **Models** title says once where most prices come from — "bundled with Coffer, updated &lt;date&gt;", or from the provider — and each model row shows its price per 1M tokens (input · output), marking only the exceptions:

- **You set** — a price you recorded on this provider; it wins over everything else. **Set price…** (or click the price) opens a small form with the input and output price and, at the bottom left, **Reset to default**, which removes it.
- **From `<provider>`** — the provider's own API reported it when its models were listed (OpenRouter does). It is refreshed each time the models are listed or refreshed, never per request.
- **Bundled · updated `<date>`** — Coffer's price list: pydantic's genai-prices, with Coffer's own Anthropic rates for the newest models. It knows prices per provider, historical prices and long-context tiers. A copy ships with each release, and the daemon refreshes it from genai-prices once a day; the date is when the data in use was taken. **Refresh model prices** in **Settings › General** turns the refresh off on a firewalled machine. No price is ever looked up while a request is being costed.
- **Local · no cost** — a model runtime on this Mac.
- **—** — nothing prices it, with **Set price…**. [Usage](/guides/usage) shows `—` for it until you set one.

### Context windows {#context-windows}

The **Window** column shows each model's context window ("1M", "128K") and where it came from. Coffer tells Claude Code and Codex this window so they compact at the right point:

- **You set** — a window you recorded for the model on this provider; it wins. Click the window, or **Set window…**, to open a form with one field in tokens (`128000`, `128k` or `1m`) and, at the bottom left, **Reset to default**, which removes it.
- **From the endpoint** — the provider reported it when its models were listed (Anthropic, OpenRouter, some gateways and local runtimes do).
- **Bundled** — the window Coffer's price list records for the model at this provider.
- **—** — nothing knows it, with **Set window…**. Coffer then writes no window, and Claude Code uses its own default (200k for a model it does not know).

An empty selection means no restriction: every model the endpoint serves. Model ids are passed to the vendor verbatim and never checked against a list inside Coffer. The one exception is a connection with a selection: if a client asks it for a model outside that selection (the Codex desktop app under a workspace model policy does this on every new thread), Coffer's proxy substitutes the agent's default model for that request and logs the swap.

What a model picker offers for an agent is decided in one place and served to every surface that offers a model choice, such as a channel's `/model` card:

- when the provider the agent runs on curates **text** models, exactly those, in your order;
- otherwise, the agent's own catalogue (see [Agents](/guides/agents#models)).

Non-text models are never offered as chat models. A provider that curates only non-text models offers no chat model at all. Reading this list never touches the network.

## One provider per agent

An agent's requests go to exactly the provider it is switched onto, through Coffer's proxy. The proxy relays the request unchanged and returns whatever the provider answers — an error included — so the agent's own retries handle transient failures; if the provider cannot be reached at all, the agent gets a 502. **Usage** meters each request on that provider. See [The local model proxy](../architecture/model-proxy.md#one-connection-one-upstream) for the details.

## Edit, rename and delete

On the provider's header:

- **Edit** changes the **Name** (any text you type, 1 to 80 characters, unique among providers ignoring case) and the addresses, with **Test** before you save. Renaming changes only the label; the page stays where it is. Adding or removing the OpenAI-compatible address changes the provider's protocol, which is locked while an agent runs on the provider. The key is not edited here.
- **Replace key…** (on the **Endpoint** section's API key row, or in the key-rejected box) checks the new key as you paste it, before saving, and overwrites the value behind the same secret — the agents' config files only name the secret, so they do not change. The API Key row shows the secret by its name (a link to its page on the Secrets page) with **Replace key…** beside it; the dialog's other choice, **Use another secret**, points this provider at another stored secret instead (the old secret and its value stay as they are, and a picked secret is not re-tested). The new value takes effect at once. See [Secret store](/guides/secret-store).
- **⋯ › Delete provider** deletes a provider nothing runs on, with its secret, after a confirmation. A provider something runs on is not blocked: **Delete provider** opens a review instead. The left side says what will happen to each user — an agent goes back to its own login, speech to text turns off, the key is deleted — and the right side shows exactly the lines Coffer will remove from each agent's config file (for Codex its model, provider table and model-list pointer; your own lines stay). **Delete** applies it: the agents are put back on their own logins first, then the provider goes. If an agent's file changed in the meantime the delete stops with the provider still there.

- **Replacing** the key overwrites the stored secret at the same ref; nothing that cites it changes.
- **Waiting for approval.** A new address for a connection whose key already goes somewhere (an added Anthropic-compatible address included), and a key another connection already uses, are saved but held until you approve them in the Coffer app. The old URL stays in use until then; a replaced key is not held.
- **Changing the protocol** (adding or removing the OpenAI-compatible address) is refused with `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` while an agent runs on the provider. Put each agent running on it (the refusal names them) back on its **Built-in login**, edit, then switch again.
- **Renaming** changes only the label. The uid, the secret ref and the agents' files stay as they are; Codex's `name = "Coffer (<name>)"` label updates on the next switch.
- **Deleting** first puts every agent that runs on the provider back on its own login, then removes the provider and deletes its secret if nothing else cites it.

## Boot self-check

The agent's recorded provider is a fact about a file Coffer does not own: the agent's CLI, other tools, you, or a restore from backup can all rewrite it. At every daemon start, Coffer checks each agent that runs on a provider. If the agent's config no longer carries Coffer's keys, Coffer clears that agent's provider, so every surface shows it on its built-in login. It does **not** write the projection back: a choice left over from an earlier session is no reason to re-route your agent through a gateway you may have stopped using. If the reverse is true — Coffer's keys are in the file while the agent runs on no provider — Coffer leaves the file alone.

After a [vault sync](/guides/vault-sync) round brings in provider changes from another machine, Coffer re-projects every agent that runs on a provider on this machine from the provider as it now is. A switch made on another machine does not arrive: which provider an agent runs on is per machine and never synced.

## Speech to text

Coffer makes one model call of its own: transcribing the voice messages that arrive through [channels](/guides/channels). It never runs a model over your knowledge or memory; your own agent does that work when you press **Tidy**. The speech-to-text model borrows the endpoint and key of one provider and names its own model. With nothing configured, a voice message reaches the agent as an audio file.

**Web UI:** open **Settings › General** and find the **Speech to text** section. Choose a provider first, then a model from that provider's list of speech models; **Off — do not transcribe** clears the model. It is a provider of its own on purpose: a chat gateway often has no transcription endpoint, so it is chosen separately from the connections your agents run on.

A choice saves as soon as you make it; there is no Save button. A line under the picker says where it stands:

- **Not set** — a provider or a model is missing, so voice messages reach the agent as audio files, without a transcript.
- **Set** — both halves are chosen and have not been tested during this visit.
- **Answering** or **Failing** — the result of **Test**. A chat request would fail on a speech model, so Test asks the provider which models it serves: it passes when the list names your model and fails when it does not. A provider that answers but lists no models reads **Reachable**, because the model can't be checked. A failure shows the reason on that line and changes nothing: the pair stays as you chose it until you pick another one.

At most one provider carries speech to text; setting it moves the flag from wherever it was. A provider can be switched into agents and carry speech to text at the same time. When the speech-to-text provider changes, the model is cleared unless the new provider's curated list includes it. The speech-to-text provider has no default: move the flag by choosing another provider.

The two memory passes that run on a timer, reading agents' memory and turning it into notes, call no model; they are switched from the **Automatic** control in the Memory header. `coffer daemon status` shows the passes running right now.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Switch fails with `CONFIG_FILE_STALE` | The agent's config changed between Coffer's read and write | Run the switch again. |
| Switch fails with `PROVIDER_DOES_NOT_REACH_AGENT` | The provider has no address for the API the agent speaks | Edit the provider and add the missing address (Anthropic-compatible for Claude Code, OpenAI-compatible for Codex), then switch again. |
| Switch fails with `PROVIDER_PROTOCOL_RETIRED` | You tried to switch an agent onto a provider that still holds the retired `ollama` protocol | Add the runtime again on its Anthropic or OpenAI protocol and delete the old provider. |
| The agent gets `503` "no connection is active" from the proxy | The provider the agent runs on no longer has an address for it, or its key is missing or waiting for approval | Check the provider's addresses and key. |
| The agent gets `401` from the proxy | The helper printed no token, or a stale one | Run the `apiKeyHelper` / `auth` command from the agent's file yourself; **Rotate proxy token** in the agent page's **⋯** menu issues a fresh one. |
| Nothing answers on `127.0.0.1:38471` | The proxy is not running | The daemon restarts a crashed proxy within a few seconds; `coffer daemon status` shows whether the daemon is up. |
| Claude Code says "There's an issue with the selected model (…)" on every turn | The provider answered 404. Usually the address Claude Code uses serves no Anthropic-compatible API (an OpenAI-compatible address such as `https://api.deepseek.com`); otherwise it does not serve that model id | `~/.coffer/logs/proxy.log` has a `model_proxy.upstream_failed … status=404` line naming the model. Edit the provider and set its **Anthropic-compatible address** (DeepSeek: `https://api.deepseek.com/anthropic`). **Change model** tests the provider at the address Claude Code uses, so one that can't serve Claude Code fails there. |
| The agent page shows the built-in login | Coffer's regular check found the agent's config no longer carries the projection, and cleared the agent's provider rather than re-route it | Switch again if you still want the provider. |

## Related

- [Agents](/guides/agents) — model binding and the agent's own catalogue
- [Usage](/guides/usage) — what requests through your providers cost, the Usage tab of this page
- [Secret store](/guides/secret-store) — where provider keys are stored
- [Conversations](/guides/chat) and [Channels](/guides/channels) — where models are picked per conversation
- [LLM Connections Are Projected Into Each Agent's Own Config File](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/provider-connections-projected-into-agent-config.md)
- Specs: [provider-switching](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/provider-switching/spec.md)
