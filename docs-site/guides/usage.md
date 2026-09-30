---
title: Usage and quota
description: What your agents spent on API-key and local providers, by model, agent or day — and how much of a subscription's allowance is left, as its vendor reports it.
---

# Usage and quota

Coffer answers two different questions, depending on how an agent is signed in:

- **An agent on a provider** — an API key for a gateway or vendor, or a local model runtime — pays per token. Coffer counts every request it makes, because every such request goes through the [local model proxy](/architecture/model-proxy).
- **An agent on its own subscription login** (a Claude or ChatGPT plan) pays a flat fee against rolling windows. What matters is how much of the five-hour and weekly allowance is left, and only the vendor's server knows that. Coffer shows the vendor's own number, never an estimate.

## The Usage page

Open **Usage** in the sidebar (under System). The page answers both questions, in two sections that load independently — if one cannot be read, the other still shows.

**Subscription quota** has one row per agent (Claude Code, Codex) with the plan it is signed in on. Each window — the five-hour and the weekly one — is a meter with how much is used and when it resets ("Resets 16:30 · in 2 h 24 min"). A window at 90% or more turns amber; one at 100% reads **Limit reached** in red. The row ends with when the number was seen and where it came from (_app-server_ for Codex, _last response_ or _status line_ for Claude Code). An agent that has not reported anything yet says **No quota reading yet**, and a window whose reset time has passed shows no number rather than a stale one. If a manual read of Codex fails — its app-server did not answer, say — the row says why, with **Try again**.

**API-key providers** covers every request that went through Coffer's local proxy:

- The period control picks **Today**, **7 days** (the default), **30 days**, **This month** or **Custom…**. A custom range is picked on a calendar; the picker notes the first day that still has per-request detail — older days keep only their daily totals, which the page still reports. The range is part of the page's address, so a refresh, a bookmark or Back keeps it.
- Five figures sum up the range: **Cost (estimated)** with the request count and how many were unpriced, **Input** (uncached), **Output** (reasoning included), **Cache read** and **Cache write** (a category only Anthropic's wire reports).
- **Cost per day** draws one bar per day of the range; hover a bar for its day and cost. Today's bar is lighter because the day is not over.
- The table breaks the range down **By model** (with the provider that served it), **By agent** or **By day**, and ends with a Total row. A model with no price reads **—** — never $0.00 — and its tooltip says why and where to set one; a cost marked `*` leaves out some unpriced requests, and a request count marked `*` includes requests whose usage never arrived. Hover the marker for the count.
- **Edit prices in Model providers** takes you to the providers, where a model's own price is set.

**Refresh** in the header re-reads everything and asks Codex for its current quota. The **⋯** menu's **Export CSV** downloads the current range in the current breakdown — the same file `coffer usage --csv` writes.

On a machine where nothing has gone through the proxy yet, the API-key section says **No API-key usage yet** and links to Model providers: switching an agent onto an API-key provider is what starts the counting. Agents on a subscription login never pass through Coffer, so for them the page only ever shows quota.

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

- Each request is priced at the price of the provider that actually answered it, taken from the first source that has one: the price **you set** on the provider (relays and resellers charge differently), free for a **local** runtime, the price the provider's **own API** reported when its models were listed, or Coffer's **bundled** price list (pydantic's genai-prices: per provider, with historical prices, long-context tiers and cache rates) — shipped with each release and refreshed once a day unless **Refresh model prices** is off in Settings › General. A price is never looked up while a request is being costed. See [Model prices](./providers.md#model-prices).
- A cache category a price leaves out is charged at its input rate, so the estimate errs high.
- A model no source prices is marked **unpriced** and counted separately — never costed at zero. Its cost reads `—` on the page and in `coffer usage` until you set a price on the provider; the dash's tooltip names the date of the price list in use.
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

Claude Code passes a statusline command the documented `rate_limits` object on every refresh. `coffer usage statusline` forwards it to Coffer and then runs your own statusline command with the same input, printing its output — so your statusline keeps working, even when the daemon is down. Coffer never installs it — the Usage page only tells you the command, it has no switch that edits your settings. To use it, set it yourself in `~/.claude/settings.json`:

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
