---
title: coffer provider
description: "Manage LLM connections and switch agents onto them"
pageClass: cli-ref
---

# coffer provider

Manage LLM connections and switch agents onto them

```sh
coffer provider [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer provider --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`provider list`](#provider-list) | List every LLM connection. |
| [`provider show`](#provider-show) | Show one connection, by name or uid. |
| [`provider add`](#provider-add) | Create an LLM connection. |
| [`provider edit`](#provider-edit) | Rename a connection, or change its title, description, endpoint, wire, key or fallback. |
| [`provider rm`](#provider-rm) | Remove a connection (its stored key goes with it when nothing else cites it). |
| [`provider enable`](#provider-enable) | Enable a connection. |
| [`provider disable`](#provider-disable) | Disable a connection. |
| [`provider scope`](#provider-scope) | Show or set which agents a connection reaches (this machine only). |
| [`provider switch`](#provider-switch) | Switch agents onto this connection and write their native config. |
| [`provider builtin`](#provider-builtin) | Switch's other half: put the agent of this type back on its OWN login. |
| [`provider detect-local`](#provider-detect-local) | Find local model runtimes (read-only: nothing is pulled or loaded). |
| [`provider order`](#provider-order) | Put providers in this order; the rest keep theirs, after them. |
| [`provider price`](#provider-price) | Show each model's price on a provider and its source, or set one. |

## provider list

List every LLM connection.

<p class="cli-label">Synopsis</p>

```sh
coffer provider list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## provider show

Show one connection, by name or uid.

<p class="cli-label">Synopsis</p>

```sh
coffer provider show [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## provider add

Create an LLM connection.

With --local the base URL must be a loopback address; Coffer detects the runtime there read-only (nothing is pulled or loaded) and records the wires it serves and each model's served context window.

For anthropic/openai/unknown supply exactly one of --secret / --secret-ref; an ollama connection needs neither. The new connection starts on the wire's own default reach; route it to specific agents (e.g. an openai gateway to Claude Code) with `coffer provider scope <name> --agents claude-code`. The model is chosen at the point of use, not on the connection.

A --secret-ref key that already goes somewhere else waits for approval in the Coffer app before this connection may send it: the command says so and exits 9, or waits for the answer with --wait.

<p class="cli-label">Synopsis</p>

```sh
coffer provider add [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Connection name |
| `--protocol` <span class="cli-chip">option</span> | text | required | Protocol: anthropic \| openai \| ollama \| unknown |
| `--base-url` <span class="cli-chip">option</span> | text | required | Upstream endpoint base URL |
| `--secret` <span class="cli-chip">option</span> | text |  | API key (stored encrypted) |
| `--secret-ref` <span class="cli-chip">option</span> | text |  | Reuse an existing secret ref instead of --secret |
| `--title` <span class="cli-chip">option</span> | text |  | Display title (≤80 chars) |
| `--description` <span class="cli-chip">option</span> | text |  |  |
| `--local` <span class="cli-chip">option</span> | flag |  | A model runtime on this machine (Ollama, LM Studio, vLLM, llama-server): detect it, curate its tool-capable models, no key needed |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |

## provider edit

Rename a connection, or change its title, description, endpoint, wire, key or fallback.

A rename changes the label and nothing else: the uid, the stored key and any projection into an agent stay where they are.

A wire change is refused while the connection is switched on, because the wire decides whether a connection can cover any agent at all. Run `coffer provider builtin <agent_type>` first, edit, then `coffer provider switch <name>` again.

A new --base-url for a connection whose key is already sent somewhere, or a new --secret for a key in use, waits for approval in the Coffer app: the change is saved, the command says what waits and exits 9, or waits for the answer with --wait.

<p class="cli-label">Synopsis</p>

```sh
coffer provider edit [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--name` <span class="cli-chip">option</span> | text |  | New name |
| `--title` <span class="cli-chip">option</span> | text |  | Display title (≤80 chars); empty clears it |
| `--description` <span class="cli-chip">option</span> | text |  |  |
| `--protocol` <span class="cli-chip">option</span> | text |  | Correct the wire format: anthropic \| openai \| ollama \| unknown |
| `--base-url` <span class="cli-chip">option</span> | text |  |  |
| `--secret` <span class="cli-chip">option</span> | text |  | Rotate the stored API key |
| `--fallback / --no-fallback` <span class="cli-chip">option</span> | boolean |  | Whether other providers' requests may fail over to this one |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |

## provider rm

Remove a connection (its stored key goes with it when nothing else cites it).

<p class="cli-label">Synopsis</p>

```sh
coffer provider rm [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--force, --yes, -f, -y` <span class="cli-chip">option</span> | flag |  | Do not ask |

## provider enable

Enable a connection.

<p class="cli-label">Synopsis</p>

```sh
coffer provider enable [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |

## provider disable

Disable a connection.

<p class="cli-label">Synopsis</p>

```sh
coffer provider disable [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |

## provider scope

Show or set which agents a connection reaches (this machine only).

<p class="cli-label">Synopsis</p>

```sh
coffer provider scope [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--agents` <span class="cli-chip">option</span> | text |  | Only these agents (a,b) |
| `--all` <span class="cli-chip">option</span> | flag |  | Every agent |
| `--none` <span class="cli-chip">option</span> | flag |  | No agent (dormant) |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## provider switch

Switch agents onto this connection and write their native config.

<p class="cli-label">Synopsis</p>

```sh
coffer provider switch [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Connection to switch onto |
| `--agent` <span class="cli-chip">option</span> | text |  | Agent type to switch: claude_code \| codex. Default: every registered, enabled agent the connection reaches |

## provider builtin

Switch's other half: put the agent of this type back on its OWN login.

Removes Coffer's projection from its native config and clears its connection. Only that agent changes. Idempotent — a no-op when the agent already runs built-in.

<p class="cli-label">Synopsis</p>

```sh
coffer provider builtin [OPTIONS] AGENT_TYPE
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `AGENT_TYPE` <span class="cli-chip">argument</span> | text | required | Agent type: claude_code \| codex |

## provider detect-local

Find local model runtimes (read-only: nothing is pulled or loaded).

<p class="cli-label">Synopsis</p>

```sh
coffer provider detect-local [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--base-url` <span class="cli-chip">option</span> | text |  | A loopback URL to probe; default: each runtime's default port |
| `--json` <span class="cli-chip">option</span> | flag |  | Machine-readable output |

## provider order

Put providers in this order; the rest keep theirs, after them.

The order is fallback priority: when an agent's model is offered by more than one enabled provider, the proxy tries the agent's own provider first, then the others in this order, before the first byte of the answer.

<p class="cli-label">Synopsis</p>

```sh
coffer provider order [OPTIONS] NAME...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME...` <span class="cli-chip">argument</span> | text (variadic) | required | Providers, first to last |

## provider price

Show each model's price on a provider and its source, or set one.

Without MODEL: every model the provider offers, with its price per 1M tokens (input · output) and where it came from — You set, From &lt;provider&gt; (its own API reported it), Bundled (the price list shipped with this release) or — when nothing prices it. With MODEL and --input/--output: record your own price, which wins over every other source. --reset removes it.

<p class="cli-label">Synopsis</p>

```sh
coffer provider price [OPTIONS] NAME [MODEL]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Provider name or uid |
| `[MODEL]` <span class="cli-chip">argument</span> | text |  | Model to set or reset |
| `--input` <span class="cli-chip">option</span> | float |  | USD per 1M input tokens |
| `--output` <span class="cli-chip">option</span> | float |  | USD per 1M output tokens |
| `--cache-read` <span class="cli-chip">option</span> | float |  | USD per 1M cache reads |
| `--cache-write` <span class="cli-chip">option</span> | float |  | USD per 1M cache writes (5-minute) |
| `--reset` <span class="cli-chip">option</span> | flag |  | Remove the price you set on MODEL |
| `--json` <span class="cli-chip">option</span> | flag |  | Machine-readable output |
