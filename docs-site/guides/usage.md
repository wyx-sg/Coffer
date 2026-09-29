---
title: Usage and quota
description: What your agents spent on API-key and local providers, by model, agent or day — and how much of a subscription's allowance is left, as its vendor reports it.
---

# Usage and quota

Coffer answers two different questions, depending on how an agent is signed in:

- **An agent on a provider** — an API key for a gateway or vendor, or a local model runtime — pays per token. Coffer counts every request it makes, because every such request goes through the [local model proxy](/architecture/model-proxy).
- **An agent on its own subscription login** (a Claude or ChatGPT plan) pays a flat fee against rolling windows. What matters is how much of the five-hour and weekly allowance is left, and only the vendor's server knows that. Coffer shows the vendor's own number, never an estimate.

## Usage of API-key and local providers

### What is counted

The proxy records one row per request it sends upstream — failed-over attempts too — with:

- the agent (from its local proxy token), the session and the provider;
- the model the agent asked for, the status and how the request ended (`completed`, `error_event`, `truncated`, `client_cancel`, `upstream_error`, `connect_error`);
- the time to first token and the duration;
- tokens in separate categories: **input** (uncached), **cache writes** (5-minute and 1-hour), **cache reads**, **output** (reasoning included), and web-search requests.

A response cut off before its final usage event is counted with usage **unknown** rather than zero. Nothing Coffer stores contains a prompt, a completion or a key.

Only traffic through the proxy is counted. Requests another tool made with the same key, or an agent made before it was switched onto the provider, are not.

### Reading it

```sh
coffer usage                          # today, by model
coffer usage --range 7d --by agent    # last 7 days, by agent
coffer usage --range month --by day   # this calendar month, day by day
coffer usage --range custom --from 2026-09-01 --to 2026-09-15
coffer usage --csv > usage.csv        # the same summary as CSV
coffer usage requests --limit 20      # the latest requests, newest first
```

Ranges are local days: **today**, **7d** and **30d** (both including today), **month** (this calendar month) and **custom** (both ends inclusive). A row per model names the provider that served it. The REST routes are `GET /api/v1/usage/summary`, `GET /api/v1/usage/requests` and `GET /api/v1/usage/export.csv`.

### Cost

Cost is an **estimate**, worked out per model and per token category:

- Coffer ships a price list with each release. It holds Anthropic's own per-model rates, including each model's cache rates.
- A provider can carry its own price for a model (on the provider's Models tab, or `price` on the curated model over REST), because relays and resellers charge differently. That price wins. A cache category it leaves out is charged at its input rate, so the estimate errs high.
- A model neither prices is marked **unpriced** and counted separately — never costed at zero. Models from vendors other than Anthropic are unpriced until you set a price.
- Each request's cost is stored with the price it was costed with, so a later price list never rewrites history.

### How long it is kept

Per-request rows are kept as long as the MCP invocation log (30 days by default; change it with `coffer config set retention.mcp_invocations <days>`). Daily totals are kept for a year.

## Subscription quota

```sh
coffer usage quota            # the latest windows per agent, with when they were seen
coffer usage quota --refresh  # ask Codex now
```

Every value is shown **as of** the moment its source produced it. With no fresh value there is no number: Coffer says when it last saw one, or that it has not. A window whose reset time has passed shows no number.

### Codex

Coffer asks Codex's own `codex app-server` (`account/rateLimits/read`), the same source Codex's `/status` uses. It reads when you ask, and in the background at most every five minutes while a Codex agent is on its own login; a manual refresh is allowed at most every 30 seconds. Sessions Coffer drives also push updates as they happen. Each window shows its used percentage, its length and when it resets.

### Claude Code

Claude Code reports its quota in the sessions Coffer drives ([chat](/guides/chat) and [channel](/guides/channels) turns): each `rate_limit_event` updates the five-hour and weekly windows. A Claude Code agent you only ever use from your own terminal therefore shows nothing — unless you opt in to the statusline wrapper below.

Coffer never reads Claude Code's or Codex's login token and never calls an undocumented usage endpoint: Anthropic's terms forbid other tools from collecting a claude.ai token, and the numbers above come without one.

### Opt-in: Claude Code's statusline

Claude Code passes a statusline command the documented `rate_limits` object on every refresh. `coffer usage statusline` forwards it to Coffer and then runs your own statusline command with the same input, printing its output — so your statusline keeps working, even when the daemon is down. Coffer never installs it; to use it, set it yourself in `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "coffer usage statusline -- ~/.claude/my-statusline.sh"
  }
}
```

With no command after `--` it prints nothing. It waits at most a second for the daemon and never starts one.

## Related

- [Model providers](/guides/providers) — switching an agent onto a provider
- [The local model proxy](/architecture/model-proxy) — how requests are relayed and metered
