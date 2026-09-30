---
title: coffer provider
description: "Manage LLM connections and switch agents onto them"
---

# coffer provider

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer provider [OPTIONS] COMMAND [ARGS]...
```

Manage LLM connections and switch agents onto them

## provider list

```sh
coffer provider list [OPTIONS]
```

List every LLM connection.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## provider show

```sh
coffer provider show [OPTIONS] NAME
```

Show one connection, by name or uid.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## provider add

```sh
coffer provider add [OPTIONS] NAME
```

Create an LLM connection.

With --local the base URL must be a loopback address; Coffer detects the runtime there read-only (nothing is pulled or loaded) and records the wires it serves and each model's served context window.

For anthropic/openai/unknown supply exactly one of --secret / --secret-ref; an ollama connection needs neither. The new connection starts on the wire's own default reach; route it to specific agents (e.g. an openai gateway to Claude Code) with `coffer provider scope <name> --agents claude-code`. The model is chosen at the point of use, not on the connection.

A --secret-ref key that already goes somewhere else waits for approval in the Coffer app before this connection may send it: the command says so and exits 9, or waits for the answer with --wait.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Connection name |
| `--protocol` | 选项 | text | 必填 | Protocol: anthropic \| openai \| ollama \| unknown |
| `--base-url` | 选项 | text | 必填 | Upstream endpoint base URL |
| `--secret` | 选项 | text |  | API key (stored encrypted) |
| `--secret-ref` | 选项 | text |  | Reuse an existing secret ref instead of --secret |
| `--title` | 选项 | text |  | Display title (≤80 chars) |
| `--description` | 选项 | text |  |  |
| `--local` | 选项 | 开关 |  | A model runtime on this machine (Ollama, LM Studio, vLLM, llama-server): detect it, curate its tool-capable models, no key needed |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

## provider edit

```sh
coffer provider edit [OPTIONS] NAME
```

Rename a connection, or change its title, description, endpoint, wire, key or fallback.

A rename changes the label and nothing else: the uid, the stored key and any projection into an agent stay where they are.

A wire change is refused while the connection is switched on, because the wire decides whether a connection can cover any agent at all. Run `coffer provider builtin <agent_type>` first, edit, then `coffer provider switch <name>` again.

A new --base-url for a connection whose key is already sent somewhere, or a new --secret for a key in use, waits for approval in the Coffer app: the change is saved, the command says what waits and exits 9, or waits for the answer with --wait.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--name` | 选项 | text |  | New name |
| `--title` | 选项 | text |  | Display title (≤80 chars); empty clears it |
| `--description` | 选项 | text |  |  |
| `--protocol` | 选项 | text |  | Correct the wire format: anthropic \| openai \| ollama \| unknown |
| `--base-url` | 选项 | text |  |  |
| `--secret` | 选项 | text |  | Rotate the stored API key |
| `--fallback / --no-fallback` | 选项 | boolean |  | Whether other providers' requests may fail over to this one |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

## provider rm

```sh
coffer provider rm [OPTIONS] NAME
```

Remove a connection (its stored key goes with it when nothing else cites it).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## provider enable

```sh
coffer provider enable [OPTIONS] NAME
```

Enable a connection.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## provider disable

```sh
coffer provider disable [OPTIONS] NAME
```

Disable a connection.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## provider scope

```sh
coffer provider scope [OPTIONS] NAME
```

Show or set which agents a connection reaches (this machine only).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--agents` | 选项 | text |  | Only these agents (a,b) |
| `--all` | 选项 | 开关 |  | Every agent |
| `--none` | 选项 | 开关 |  | No agent (dormant) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## provider switch

```sh
coffer provider switch [OPTIONS] NAME
```

Switch the agents this connection reaches onto it and write their native config.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Connection to activate |

## provider builtin

```sh
coffer provider builtin [OPTIONS] AGENT_TYPE
```

Switch's other half: put every agent of this type back on its OWN login.

Removes Coffer's projection from the native config and clears the active connection covering it. Idempotent — a no-op when the agent already runs built-in.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `AGENT_TYPE` | 参数 | text | 必填 | Agent type: claude_code \| codex |

## provider detect-local

```sh
coffer provider detect-local [OPTIONS]
```

Find local model runtimes (read-only: nothing is pulled or loaded).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--base-url` | 选项 | text |  | A loopback URL to probe; default: each runtime's default port |
| `--json` | 选项 | 开关 |  | Machine-readable output |

## provider order

```sh
coffer provider order [OPTIONS] NAME...
```

Put providers in this order; the rest keep theirs, after them.

The order is fallback priority: when an agent's model is offered by more than one enabled provider, the proxy tries the agent's own provider first, then the others in this order, before the first byte of the answer.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME...` | 参数 | text（可变个数） | 必填 | Providers, first to last |

## provider price

```sh
coffer provider price [OPTIONS] NAME [MODEL]
```

Show each model's price on a provider and its source, or set one.

Without MODEL: every model the provider offers, with its price per 1M tokens (input · output) and where it came from — You set, From &lt;provider&gt; (its own API reported it), Bundled (the price list shipped with this release) or — when nothing prices it. With MODEL and --input/--output: record your own price, which wins over every other source. --reset removes it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Provider name or uid |
| `[MODEL]` | 参数 | text |  | Model to set or reset |
| `--input` | 选项 | float |  | USD per 1M input tokens |
| `--output` | 选项 | float |  | USD per 1M output tokens |
| `--cache-read` | 选项 | float |  | USD per 1M cache reads |
| `--cache-write` | 选项 | float |  | USD per 1M cache writes (5-minute) |
| `--reset` | 选项 | 开关 |  | Remove the price you set on MODEL |
| `--json` | 选项 | 开关 |  | Machine-readable output |
