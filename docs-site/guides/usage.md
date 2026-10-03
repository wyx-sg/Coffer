---
title: Usage
description: What your agents spent through API-key and local providers, by model, agent or day, on the Usage tab of Model providers.
---

# Usage

What your agents spent through an API-key or local provider is counted by Coffer, because every such request goes through the [local model proxy](/architecture/model-proxy).

An agent on its own subscription login (a Claude or ChatGPT plan) never passes through Coffer, so Coffer shows nothing for it. How much of a plan's allowance is left is something only the vendor knows; read it in the vendor's own app.

## The Usage tab

Open **Model providers** in the sidebar and switch to its **Usage** tab (address `/model-providers?tab=usage`). The page covers every request that went through Coffer's local proxy:

- The period control picks **Today**, **Last 7 days** (the default), **Last 30 days**, **This month** or **Custom range…**. A custom range is picked on a calendar and reaches up to 90 days back; the picker notes the first day that still has per-request detail, because older days keep only their daily totals. Beside it, the **Agent** and **Provider** pills narrow everything below to one agent and one provider. The range, the filters and the breakdown are part of the page's address, so a refresh, a bookmark or Back keeps them.
- Four figures sum up the range: **Cost (estimated)** with the request count and how many models were unpriced, **Input** (uncached), **Output** (reasoning included), **Cache read** and **Cache write** (a category only Anthropic's wire reports).
- **Cost per day** draws one bar per day of the range; hover a bar for its day and cost. Today's bar is lighter because the day is not over.
- The table breaks the range down **By model** (with the provider that served it, and in **By** the agents that used it), **By agent** or **By day** (newest first, with each day's top agent; the latest week shows first, "Showing 7 of N days", and **Show all** lists the rest), and ends with a Total row, the cost of the priced models. A model with no price reads **—**, never $0.00, and its tooltip says why and where to set one; a cost marked `*` leaves out some unpriced requests, and a request count marked `*` includes requests whose usage never arrived. Hover the marker for the count.
- **Edit prices** at the foot of the table takes you to the providers, where a model's own price is set.
- **Export CSV** next to the filters downloads the current range, filters and breakdown, the same file `coffer usage --csv` writes with the same options.

On a machine where nothing has gone through the proxy yet, the tab is only its empty state, **No API-key usage yet**, with no range or filters to narrow, and a link to **Providers**: switching an agent onto an API-key provider is what starts the counting.

## What is counted

The proxy records one row per request it sends upstream — failed-over attempts too — with:

- the agent (from its local proxy token), the session and the provider;
- the model the agent asked for, the status and how the request ended (`completed`, `error_event`, `truncated`, `client_cancel`, `upstream_error`, `connect_error`);
- the time to first token and the duration;
- tokens in separate categories: **input** (uncached), **cache writes** (5-minute and 1-hour), **cache reads**, **output** (reasoning included), and web-search requests.

A response cut off before its final usage event is counted with usage **unknown** rather than zero. Nothing Coffer stores contains a prompt, a completion or a key.

Only traffic through the proxy is counted. Requests another tool made with the same key, or an agent made before it was switched onto the provider, are not.

## Reading it

```sh
coffer usage                          # today, by model
coffer usage --range 7d --by agent    # last 7 days, by agent
coffer usage --range month --by day   # this calendar month, day by day
coffer usage --range custom --from 2026-09-01 --to 2026-09-15
coffer usage --agent codex --provider openai   # only Codex's requests through the provider "openai"
coffer usage --csv > usage.csv        # the same summary as CSV
coffer usage requests --limit 20      # the latest requests, newest first
```

Ranges are local days: **today**, **7d** and **30d** (both including today), **month** (this calendar month) and **custom** (both ends inclusive). A row per model names the provider that served it; every row lists the agents that sent its requests, most first. `--agent` takes an agent type (`claude_code`, `codex`) and `--provider` a provider's name; over REST they are the `agent_type` and `connection_uid` query parameters of the summary and the CSV. The REST routes are `GET /api/v1/usage/summary`, `GET /api/v1/usage/requests` and `GET /api/v1/usage/export.csv`.

## Cost

Cost is an **estimate**, worked out per model and per token category:

- Each request is priced at the price of the provider that actually answered it, taken from the first source that has one: the price **you set** on the provider (relays and resellers charge differently), free for a **local** runtime, the price the provider's **own API** reported when its models were listed, or Coffer's **bundled** price list (pydantic's genai-prices: per provider, with historical prices, long-context tiers and cache rates) — shipped with each release and refreshed once a day unless **Refresh model prices** is off in Settings › General. A price is never looked up while a request is being costed. See [Model prices](./providers.md#model-prices).
- A cache category a price leaves out is charged at its input rate, so the estimate errs high.
- A model no source prices is marked **unpriced** and counted separately — never costed at zero. Its cost reads `—` on the page and in `coffer usage` until you set a price on the provider; the dash's tooltip names the date of the price list in use.
- Each request's cost is stored with the price it was costed with, so a later price list never rewrites history.

## How long it is kept

Per-request rows are kept as long as the MCP invocation log (30 days by default; change it with `coffer config set retention.mcp_invocations <days>`). Daily totals are kept for a year.

## Related

- [Model providers](/guides/providers) — switching an agent onto a provider
- [The local model proxy](/architecture/model-proxy) — how requests are relayed and metered
