---
title: Usage
description: What your agents spent on API-key and local providers, by model, agent or day — the Usage tab of Model providers.
---

# Usage

Usage is the second tab of **Model providers**, at `/model-providers?tab=usage`. It answers one question: what did the requests your agents sent through an API-key or local provider cost? An agent on a provider pays per token, and Coffer counts every request it makes, because every such request goes through the [local model proxy](/architecture/model-proxy). Agents on their own subscription login never pass through Coffer, so they do not appear here.

## The Usage tab

Open **Model providers** and choose **Usage** beside **Providers**. The page header — the title, the **Experimental** tag and **Add provider** — is the same one the Providers tab has. There is no Usage entry in the sidebar.

- The filter row starts with the **time range** — **Today**, **Last 7 days** (the default), **Last 30 days**, **This month** or **Custom range…**, picked as dates on a calendar that reaches up to 90 days back; the picker notes the first day that still has per-request detail, since older days keep only their daily totals, which the page still reports. Next come **Agent** and **Provider**, which narrow everything below to one agent and one provider. The range, the filters and the breakdown are part of the page's address, so a refresh, a bookmark or Back keeps them. There is no Refresh button: the numbers are Coffer's own.
- Five figures sum up the range: **Cost (estimated)** — its help tip says how the estimate is worked out — with the request count, **Input** (uncached), **Output** (reasoning included), **Cache read** and **Cache write** (a category only Anthropic's wire reports). If some models have no price, **1 model unpriced** appears once, in the Cost figure, as a link to that model on its provider, where you set one; nothing else on the page repeats it.
- **Cost per day** draws one bar per day of the range; hover a bar for its day and cost. Today's bar is lighter because the day is not over.
- The table breaks the range down **By model** (with the provider that served it, and the agents that used it), **By agent** or **By day** (newest first; the latest week shows first and **Show all** lists the rest), and ends with a Total row — the cost of the priced models. A model with no price reads **—** — never $0.00 — and its tooltip says why and where to set one; a cost marked `*` leaves out some unpriced requests, and a request count marked `*` includes requests whose usage never arrived. Hover the marker for the count.

On a machine where nothing has gone through the proxy yet, the tab is only its empty state — **No API-key usage yet**, with **Open Providers** and no range or filters to narrow: switching an agent onto an API-key provider is what starts the counting. With the Models [experimental feature](/guides/experimental-features) off, the tab and the page are absent like the rest of the feature.

## Usage of API-key and local providers

### What is counted

The proxy records one row per request, with:

- the agent (from its local proxy token), the session and the provider;
- the model the agent asked for, the status and how the request ended (`completed`, `error_event`, `truncated`, `client_cancel`, `upstream_error`, `connect_error`);
- the time to first token and the duration;
- tokens in separate categories: **input** (uncached), **cache writes** (5-minute and 1-hour), **cache reads**, **output** (reasoning included), and web-search requests.

A response cut off before its final usage event is counted with usage **unknown** rather than zero. Nothing Coffer stores contains a prompt, a completion or a key.

Only traffic through the proxy is counted. Requests another tool made with the same key, or an agent made before it was switched onto the provider, are not.

## Ranges and REST

Ranges are local days: **today**, **7d** and **30d** (both including today), **month** (this calendar month) and **custom** (both ends inclusive), the same choices as the time-range picker. A row per model names the provider that served it; every row lists the agents that sent its requests, most first. Over REST, the agent and provider filters are the `agent_type` and `connection_uid` query parameters of the summary. The REST routes are `GET /api/v1/usage/summary` and `GET /api/v1/usage/requests`.

## Cost

Cost is an **estimate**, worked out per model and per token category:

- Each request is priced at the price of the provider that actually answered it, taken from the first source that has one: the price **you set** on the provider (relays and resellers charge differently), free for a **local** runtime, the price the provider's **own API** reported when its models were listed, or Coffer's **bundled** price list (pydantic's genai-prices: per provider, with historical prices, long-context tiers and cache rates) — shipped with each release and refreshed once a day unless **Refresh model prices** is off in Settings › General. A price is never looked up while a request is being costed. See [Model prices](./providers.md#model-prices).
- A cache category a price leaves out is charged at its input rate, so the estimate errs high.
- A model no source prices is marked **unpriced** and counted separately — never costed at zero. Its cost reads `—` on the tab until you set a price on the provider.
- Each request's cost is stored with the price it was costed with, so a later price list never rewrites history.

## How long it is kept

Per-request rows are kept as long as the MCP invocation log (30 days by default; change it under **Settings → Data → History**). Daily totals are kept for a year.

## Related

- [Model providers](/guides/providers) — switching an agent onto a provider
- [The local model proxy](/architecture/model-proxy) — how requests are relayed and metered
