---
title: The local model proxy
description: How an agent on an API-key or local connection reaches its model — a small supervised process on loopback that relays each request byte for byte, injects the real key, fails over only before the first content byte, and meters every request without recording what was said.
---

# The local model proxy

An agent on its own login talks to its vendor directly, and Coffer stays out of the way. An agent that Coffer switches onto a **connection** — an API key for a gateway, a vendor account, or a model runtime on this machine — talks to the **local model proxy** instead. The proxy is a small process on `127.0.0.1`. It forwards each request to the connection's endpoint with the real key attached, and writes down what the request cost.

The decisions and the options weighed are in two ADRs: [API-Key Providers Are Reached Through a Separate Local Model Proxy That Relays Bytes Unchanged](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/api-key-providers-are-reached-through-a-separate-local-model-proxy.md) and [Usage Is Metered at the Proxy; Subscription Agents Are Not Metered](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota.md). This page explains how it works.

## Why a proxy at all

Before the proxy, Coffer wrote the connection's endpoint straight into each agent's config. Claude Code also got a helper command that printed the real key, and Codex got the real key in its environment. That arrangement could not do three things:

- **Meter.** Nothing Coffer ran saw the requests, so it could not say what an agent spent.
- **Fail over.** Nothing was in the request path to move a failing request somewhere healthy.
- **Keep the key away from the agent.** A prompt-injected agent could run the helper, or `env`, and read the key.

With the proxy in the path, the agent holds only a **local token** that unlocks the loopback proxy and nothing else. The real key stays with Coffer.

## The shape

```
Claude Code ──► http://127.0.0.1:38471/anthropic/v1/messages ──┐
                 (apiKeyHelper: coffer proxy token …)          │   same wire,
                                                               ├─► same bytes ──► the connection's endpoint
Codex ──► http://127.0.0.1:38471/openai/v1/responses ───────────┘   + the real key
           (auth: coffer proxy token …)
```

- **A separate process, from the daemon's binary.** A frozen build runs the proxy as `coffer-daemon proxy`, so there is no fourth binary to build and sign; from source it is `python -m coffer.infrastructure.model_proxy.entry`. It is its own process because the daemon restarts on every upgrade and runs migrations at start. A proxy inside the daemon would cut every in-flight model stream at each restart, including sessions in the user's own terminal.
- **Supervised by the daemon.** At start the daemon reads `~/.coffer/proxy.json` (`port`, `pid`, `started_at`, `version` and a control token, mode `0600`). If a proxy of the same version answers there, the daemon re-attaches to it. If the proxy is from another build, the daemon asks it to drain and replaces it once it has exited. If none is running, the daemon spawns one. A health check every few seconds restarts a crashed proxy. When the daemon stops, it stops *supervising*; the proxy keeps running.
- **A fixed port.** The proxy binds `127.0.0.1:38471` by default (`proxy_port` in `daemon-config.json`). A fixed port keeps the URL written into the agents' files from moving on its own. There is no option to bind another interface.

## What the agents are given

**Claude Code** (`settings.json`):

- `env.ANTHROPIC_BASE_URL` is `http://127.0.0.1:<port>/anthropic`.
- `apiKeyHelper` is `<coffer> proxy token --agent-uid <uid>`. Claude Code sends its output as both `x-api-key` and `Authorization`, and caches it for five minutes.
- `env.NO_PROXY` gains `127.0.0.1,localhost`, so a corporate `HTTPS_PROXY` never captures the loopback leg.
- The model keys (`model`, `effortLevel`, the tier pins, `modelPicker`) come from the agent's binding, as described in [Model providers](/guides/providers#what-gets-written).

**Codex** (`config.toml`):

- `[model_providers.coffer]` has `base_url = "http://127.0.0.1:<port>/openai/v1"`, `wire_api = "responses"`, `supports_websockets = false` and `requires_openai_auth = false`.
- `auth = { command = "<coffer>", args = ["proxy", "token", "--agent-uid", "<uid>"] }`, so a Codex started in any terminal fetches its own token and nothing has to be exported. The command-backed `auth` table needs Codex 0.155.1 or later.

Neither file names the connection. Switching an agent from one API-key connection to another changes the proxy's **route** and leaves the agent's file alone. Switching between a connection and the agent's own login is still a file write.

An agent on its own subscription login is never pointed at the proxy. The proxy would refuse its credential anyway (below).

## Tokens

Each managed agent has its own random 256-bit token, minted on first use. It is kept as Fernet ciphertext in the secret store under `proxy-token/<agent name>` (`proxy-token/claude-code`, `proxy-token/codex`; an agent's name is fixed), a machine-local ref that vault sync never carries. A token whose agent is gone is deleted the next time the proxy's state is built.

- `coffer proxy token --agent-uid <uid>` prints the token. It is the command both agents run.

The proxy is never given the tokens themselves, only their SHA-256 digests, and it compares the digest of what a request presents in constant time.

The token is not a security boundary against a process of the same user: anything that can read the agent's config can run the command. It exists to keep browser pages and other users' processes off the proxy, to say which agent made a request, and to fill the key field both agents insist on.

## The relay

The rules come from the agents' own gateway contracts. Claude Code's are the strictest.

- **Same wire in, same wire out.** The Anthropic routes forward only to an Anthropic-shaped endpoint (`/v1/messages`, `/v1/messages/count_tokens`, `/v1/models`), and the Responses route only to a Responses endpoint (`/v1/responses`). There is no protocol translation. Translation is where other gateways' bugs live: mangled tool-call deltas, dropped thinking signatures, zeroed usage.
- **The body is forwarded byte for byte.** The proxy parses a *copy* only to read `model` and `stream`. Nothing is allow-listed, reordered or re-serialised, so `anthropic-beta` values and body fields Coffer has never heard of arrive untouched, and prompt caching and thinking signatures keep working.
- **Headers pass except for a short list.** Everything is forwarded except hop-by-hop headers, `host`, `content-length`, the client's credentials (`authorization`, `x-api-key`, cookies) and `accept-encoding`. The proxy asks for an uncompressed stream so its usage reader sees plain SSE. The connection's key is then injected: `x-api-key` plus `Authorization: Bearer` on the Anthropic wire, `Authorization: Bearer` on the Responses wire, and nothing for a keyless local runtime.
- **Responses come back as received.** Status, headers and body chunks are relayed unbuffered, including pings and SSE comments. Claude Code aborts a stream that is silent for 300 seconds, counting relayed bytes. Error bodies are relayed verbatim, because both agents' recovery logic matches the upstream's wording.
- **Timeouts.** 10 seconds to connect, no total timeout, and at least 300 seconds of read idleness, matching both agents' own watchdogs.

Besides the model routes, the proxy answers `/api/hello` and `/anthropic/api/hello` (Claude Code's warm-up probe, without auth) and the daemon's control routes `/_coffer/health`, `/_coffer/state` and `/_coffer/drain` (behind the control token). Everything else the proxy is asked for is 404. The endpoint of a connection is its `base_url` with one trailing `/v1` dropped, so `https://api.anthropic.com`, `https://api.openai.com/v1` and a local `http://127.0.0.1:11434/v1` all resolve the way each wire's clients expect.

## Refusals

Before anything is forwarded, the proxy refuses:

- a `Host` that is not a loopback name on the port the request arrived on (DNS rebinding), with 403;
- any request that carries an `Origin` header, with 403. No browser page is a client of the proxy;
- a request without a Coffer token, with 401 in the wire's own error shape. That includes a claude.ai OAuth token (`sk-ant-oat…`) and a real provider key. The proxy never forwards a client's credential.

## Failover

A request can fail over only **before the first content byte** reaches the agent. The proxy holds a streamed response until its first content event — `content_block_start` on the Anthropic wire, the first output item or delta on the Responses wire — bounded to 64 KiB and 5 seconds, so an error that arrives first can still be retried invisibly. Past either bound the proxy stops holding and relays what it has. After the first content byte the proxy never switches. The error or truncation goes to the agent, and the agent's own retry lands on a healthy member, because the failure has marked this one.

- **What fails over:** a connect, TLS or DNS error; a 5xx, 529 or 429 status; 401 or 403 (the key is at fault, not the request); a first-byte timeout; an error event before the first content event.
- **What never fails over:** 400, 404 and 413. The request is at fault, so a retry elsewhere would fail the same way.
- **Where it goes:** the next member of the agent's route. The agent's own connection is first. After it come the other enabled connections that reach the same agent type, speak the same protocol, have **Use as a fallback** switched on, and list the requested model among their curated models — in the order of the Model providers list, which the user sets. Failover never changes the model. A local runtime has no fallback members and is never one, so a prompt meant for a local model never leaves the machine by failing over.
- **Where it is recorded:** each usage record carries a `relay_id` shared by every attempt at one request. On ingest the daemon files a `provider_failover` audit row for each attempt that failed over, naming the provider the request went to next, and Activity shows it. Usage is metered on the provider that answered.
- **No retry storms:** one pass over the pool per request, and never the same member twice. Both agents already retry on their own.
- **Member health:** a 429 with `retry-after` cools that member for that long. 401 or 403 disables it until its key changes. Other failures cool it briefly.
- **Session affinity:** a session (`x-claude-code-session-id`, Codex's `session_id`) stays on one member until that member fails, which keeps the prompt cache warm.

When every member has failed, the last upstream response is relayed verbatim. When none answered at all, the agent gets a 502 in its wire's own error shape.

## Metering

A usage reader consumes a copy of the bytes beside the relay. If the reader fails, the relay is unaffected. The proxy writes one record per upstream attempt, failed-over attempts included:

- **Who:** the agent (from its token), the session and request class where the agent sends them, and the connection.
- **What:** the endpoint and the requested model.
- **How it went:** the status, the outcome (`completed`, `error_event`, `truncated`, `client_cancel`, `upstream_error`, `connect_error`), the time to first token and the duration.
- **Tokens:** counted in disjoint categories: uncached input, 5-minute and 1-hour cache writes, cache reads, and output (of which reasoning is a part). They are read by each wire's own rules. On the Anthropic wire, `message_delta` overrides `message_start`, because server tools restate and extend the totals. On the Responses wire, the terminal `response.completed` / `incomplete` / `failed` event carries them, and cached tokens are split out of `input_tokens`.

A stream cut before its terminal event is recorded with usage **unknown**. It is never dropped and never guessed.

The proxy opens no database. It appends records to spool files under `~/.coffer/proxy-usage/`, and a file is renamed from `.jsonl.part` to `.jsonl` once complete. The daemon, the only database writer, ingests completed files, deletes each only after its rows are committed, and de-duplicates by the upstream's request id, so a repeated ingest writes nothing twice. How the records become the usage report is in [Usage and quota](/guides/usage).

## What it records, and what it never does

The proxy's logs and records carry metadata only: the usage record above, and each failover decision. It never records a body, a prompt, a completion or a secret.

The daemon decrypts the keys of the connections the proxy serves and pushes them over the proxy's authenticated loopback control route, on spawn, on re-attach, after every reconcile pass, and as soon as a secret approval is applied in the desktop app. A connection whose key waits for approval — a new key for one in use, or a base URL the key has not gone to before — is left out of the pushed state, so the proxy keeps sending the old key, or sends nothing to the new URL, until you approve; the next request after the approval uses the new key or URL, with no restart of the daemon or the proxy. The proxy holds the keys in memory only. It never writes them to disk, argv, the environment or a log, and it never holds the master key.

## Local model runtimes

A connection to a runtime on this machine goes through the proxy like any other. Ollama, LM Studio, vLLM and llama.cpp's `llama-server` all qualify, each speaking its native protocol. Such a connection carries no key, or an optional one, and has no fallback members. Every mainstream runtime now serves both Anthropic Messages and OpenAI Responses itself, so no translation is needed. A runtime that speaks only Chat Completions (`mlx_lm.server`) is not a supported upstream; use LM Studio's MLX engine instead. Detection and setup are in [Model providers](/guides/providers#local-model-runtimes).
