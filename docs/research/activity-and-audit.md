# Activity, audit and retention: how other products do it

**Feature**: letting a user see what happened on their machine's agent vault — an audit log of configuration changes with an actor, a log of tool invocations without payloads, daemon/app logs, retention, and a UI to browse, filter and correlate them · **Coffer spec**: [resource-framework](../../openspec/specs/resource-framework/spec.md) (audit, retention), [web-ui](../../openspec/specs/web-ui/spec.md) (Activity page), [daemon](../../openspec/specs/daemon/spec.md) (daemon log) · **Related ADRs**: [audit-and-retention](../decisions/audit-and-retention.md)
**Researched**: 2026-09 · **Method**: web research, primary sources

The field splits into three families that each solve one slice of this feature:

1. **LLM/agent observability platforms** (Langfuse, Arize Phoenix, LangSmith, Helicone, AgentOps) — trace trees of model and tool calls, sessions, retention by project. Their governance surface (the audit log of *who changed what*) is almost always the paid tier.
2. **Standards and agent-native telemetry** (OpenTelemetry GenAI + MCP semantic conventions, Claude Code's OTel export, Codex's `[otel]` block, the MCP logging utility, Docker MCP Gateway) — what a tool call record looks like, and what is redacted by default.
3. **SaaS admin audit logs** (GitHub, 1Password, Tailscale, Cloudflare) — the mature reference for the *configuration* audit log: actor/action/target/diff, fixed retention windows, qualifier search, streaming export.

Star counts are as of 2026-09.

---

## 1. LLM/agent observability platforms

### Langfuse (~35k stars, MIT core + `ee/` folders; acquired by ClickHouse, Jan 2026)

**Data model.** A **trace** is one request/operation and is "the logical grouping of all observations that share the same `trace_id`". **Observations** are the steps inside it (generic spans, *generations* for LLM calls, *events*, tool calls, retrievals) and nest via parent ids. A **session** is an optional one-to-many grouping of traces (a multi-turn conversation). Traces carry environment, tags, user id, free-form metadata and release/version for filtering. Ingestion is OpenTelemetry-based: SDKs batch spans in the background and short-lived processes must call `flush()` before exit or lose data. ([data model](https://langfuse.com/docs/observability/data-model))

**Storage.** Self-host runs ClickHouse (traces/observations), Postgres (config, users), Redis (queue) and S3-compatible blob storage. ([repo](https://github.com/langfuse/langfuse)) In January 2026 ClickHouse acquired Langfuse; the stated plan is to stay MIT and self-hostable. ([Langfuse blog](https://langfuse.com/blog/joining-clickhouse), [ClickHouse blog](https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability))

**Payload privacy.** Inputs/outputs are captured by default. Redaction is **client-side**: a `mask` function (JS) or `mask_otel_spans` hook (Python) rewrites `input`, `output` and `metadata` before export; alternatively the OTel Collector's redaction/attributes processors can scrub centrally. Masking changes the exported record, not the app's runtime values. ([masking](https://langfuse.com/docs/observability/features/masking)) Server-side masking is an Enterprise feature. ([license key](https://langfuse.com/self-hosting/license-key))

**Audit log (paywalled).** Captures actor ("user or API key that performed the action"), action (create/update/delete/resource-specific), timestamp, and for updates the **full before and after state** of the resource as JSON. Viewer filters by time and project, paginates, and exports from the UI; requires `auditLogs:read` (owners/admins). Available **only** on Cloud Enterprise or self-hosted Enterprise Edition. ([audit logs](https://langfuse.com/docs/administration/audit-logs))

**Retention.** Per project, minimum 3 days. A **nightly job** deletes traces, observations, scores and media older than the window; **audit logs and dataset items are exempt** even when their source traces expire. Retention management is Pro/Enterprise on Cloud and Enterprise-licensed on self-host; without a policy, self-hosted data is kept **indefinitely**, Cloud keeps 30 d (Hobby) / 90 d (Core) / 3 y (Pro+). ([data retention](https://langfuse.com/docs/administration/data-retention), [pricing](https://langfuse.com/pricing))

Enterprise-licence features on self-host: project-level RBAC, audit logs, data retention policies, server-side masking, SCIM/org APIs, UI customization. ([license key](https://langfuse.com/self-hosting/license-key))

### Arize Phoenix (~11.6k stars, Elastic License 2.0)

**Model.** OpenTelemetry tracing using the **OpenInference** conventions; projects contain traces of spans; sessions group multi-turn traces. **Storage is SQLite for local use, Postgres for production** — the only major platform whose single-user mode is a single embedded file, which makes it the closest architectural analogue to a local vault. ([repo](https://github.com/Arize-ai/phoenix))

**Retention.** Policies are either **time-based (days)** or **trace-count-based (max N traces)**. A deployment-wide "Default" policy is set by `PHOENIX_DEFAULT_RETENTION_POLICY_DAYS` (0 = indefinite, the default); projects can override it in a Data Retention tab. Each policy has its **own cron schedule** (admins pick off-hours). When a sweep deletes a session's last trace, the empty session is removed too. Users can also manually delete traces older than a chosen date from the project menu or REST. Postgres space is only reclaimed by vacuum later. ([data retention](https://arize.com/docs/phoenix/settings/data-retention))

**Payload privacy.** OpenInference defines environment switches honoured by all instrumentors: `OPENINFERENCE_HIDE_INPUTS` replaces `input.value` with `__REDACTED__` and drops input messages and tool definitions; `OPENINFERENCE_HIDE_OUTPUTS` does the same for outputs; finer flags drop only message arrays (`HIDE_INPUT_MESSAGES`, `HIDE_OUTPUT_MESSAGES`) while keeping finish reasons etc. The span, its timing and its status survive. ([configuration spec](https://github.com/Arize-ai/openinference/blob/main/spec/configuration.md))

### LangSmith (closed source; SaaS + Enterprise self-host)

**Run model.** Every span is a **run** with `id`, `trace_id`, `parent_run_id`, `run_type` (`llm`, `chain`, `tool`, `retriever`, `embedding`, `prompt`, `parser`), `inputs`/`outputs`, `start_time`/`end_time`, `status` (`success`/`error`/`pending`), tags, `extra`. The notable trick is **`dotted_order`**: `<start>Z<uuid>.<child_start>Z<child_uuid>…` — a single lexicographically sortable string whose first UUID is the trace id, last is the run id and penultimate the parent. One string gives both chronological sort and tree reconstruction without a recursive query. ([run data format](https://docs.langchain.com/langsmith/run-data-format))

**Threads.** Traces are grouped into a thread by metadata key `session_id` or `thread_id` (UUID v7 recommended), which **must be propagated to every child run** or thread-level filtering and token counts break. Three views: *Trajectory* (chat-style), *Turns* (one card per turn), *Details* (per-run inputs/outputs/timing inside thread context), switched with `T`/`D`; thread lists show turn count, P50/P99 latency, tokens, cost, feedback. ([threads](https://docs.langchain.com/langsmith/threads))

**Payload privacy.** `LANGSMITH_HIDE_INPUTS=true` / `LANGSMITH_HIDE_OUTPUTS=true` keep the run tree (tool usage still shown) but drop content; there is also metadata hiding and regex/anonymizer-based masking in the SDK. ([mask inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs))

**Retention.** Historically two tiers: *base* traces 14 days, *extended* 400 days (upgrading is billed). From **2026-09-14 the SaaS maximum drops to 180 days** (selectable 30–180 d); self-host TTL defaults are unchanged. ([support: extended retention](https://support.langchain.com/articles/3206725817-why-are-my-traces-being-automatically-upgraded-to-extended-retention), [docs PR #5859](https://github.com/langchain-ai/docs/pull/5859))

**Audit log (Enterprise only).** Tamper-resistant record of **administrative/write** operations (200+ operation types: API keys, roles, SSO, workspaces, datasets…), **read operations largely excluded**. Stored in Postgres, emitted in **OCSF 1.7.0 API Activity** format (`actor.user.uid`, `api.operation`, `status`, `resources`, plus `unmapped.original_audit_log` for the native record) so SIEMs ingest it directly. UI under Organization Settings and `GET /api/v1/audit-logs` with filters for time range, workspace, operation, actor, resource id. **400-day retention, separate from trace retention** (it was explicitly left at 400 d when traces went to 180 d). ([audit logs](https://docs.langchain.com/langsmith/audit-logs))

### Helicone (~6.2k stars, Apache-2.0; acquired by Mintlify 2026-03-03, maintenance mode)

**Mechanism.** A **proxy/gateway**: the app points its LLM base URL at Helicone, which logs each request. Architecture: Cloudflare Workers edge, "Jawn" Express server for log collection, Supabase (Postgres + auth), ClickHouse for analytics. ([repo](https://github.com/Helicone/helicone))

**Sessions via headers.** Three request headers build a tree without any SDK: `Helicone-Session-Id` (groups requests), `Helicone-Session-Path` (slash path such as `/conversation/followup/clarify` encoding parent/child), `Helicone-Session-Name`. Paths are *types of work*, not chronology — "group by function, not by time". ([sessions](https://docs.helicone.ai/features/sessions))

**Payload privacy.** `Helicone-Omit-Request: true` / `Helicone-Omit-Response: true` drop bodies from storage while still computing cost, latency and tokens — but the docs are explicit that the payload **still transits** Helicone's backend. ([omit logs](https://docs.helicone.ai/features/advanced-usage/omit-logs))

**Retention.** Tiered: Hobby 7 days, Pro 1 month, Team 3 months (per third-party pricing summaries; Helicone's own pricing page was not re-verified). **Status:** after the Mintlify acquisition the hosted service stays up in maintenance mode — security fixes, new models, bug fixes only. ([Helicone blog](https://www.helicone.ai/blog/joining-mintlify))

### AgentOps (~5.8k stars, MIT, dashboard + backend open source)

**Model.** OpenTelemetry-based SDK with a fixed span taxonomy: `SESSION` (root, created by `agentops.init()`), `AGENT`, `WORKFLOW`, `OPERATION`/`TASK`, `LLM`, `TOOL`, attached via decorators (`@session`, `@agent`, `@operation`, `@task`, `@workflow`). LLM spans auto-capture model, provider, token counts, cost **and messages**, plus host environment (OS, Python version, hostname). ([core concepts](https://docs.agentops.ai/v2/concepts/core-concepts), [repo](https://github.com/AgentOps-AI/agentops))

**UX.** The headline feature is **session replay** — a step-by-step execution graph/waterfall of one session for time-travel debugging.

**Retention.** Free tier 5,000 events/month; Pro "unlimited log retention"; Enterprise "custom data retention policy". ([agentops.ai](https://www.agentops.ai/)) No documented content-redaction switch was found.

---

## 2. Standards and agent-native telemetry

### OpenTelemetry GenAI and MCP semantic conventions (status: Development)

The conventions moved to a dedicated repo, [`open-telemetry/semantic-conventions-genai`](https://github.com/open-telemetry/semantic-conventions-genai) (~390 stars), covering spans, events, metrics, agent spans, MCP and provider-specific conventions. **All of it is still "Development", not stable** — attribute names can change. ([GenAI spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md))

**GenAI spans.** Required `gen_ai.operation.name` and `gen_ai.provider.name`, conditionally `gen_ai.request.model`; span names `{operation} {model}`; operation kinds include inference, embeddings, retrieval, execute-tool, memory operations, and agent spans (create/invoke agent, invoke workflow). `gen_ai.conversation.id` is set **only if the library already has one** — instrumentations must not invent a fallback id. Token usage splits input/output, cached, and per-modality counts. **Message content is opt-in and off by default**; instrumentations may upload large content to external storage and record a reference instead of inlining it. ([GenAI spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md))

**MCP spans** (the most directly reusable shape for a gateway's invocation record). ([MCP conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md))
- Span name `{mcp.method.name} {target}` (e.g. `tools/call search`), CLIENT on the caller, SERVER on the callee.
- Attributes: `mcp.method.name` (required), `mcp.session.id`, `gen_ai.tool.name`, `jsonrpc.request.id`, `mcp.resource.uri`, `error.type` on failure, `network.transport`, server/client address and port.
- **Opt-in only**: `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result`.
- **Context propagation through `params._meta`**: W3C `traceparent`, `tracestate` and `baggage` are injected unprefixed into the request's `_meta`; servers extract them to parent their SERVER span. This is how a trace crosses a proxy hop.
- Metrics: `mcp.client.operation.duration`, `mcp.server.operation.duration`, `mcp.client.session.duration`, `mcp.server.session.duration`.
- The conventions describe the MCP lifecycle up to protocol 2025-06-18; aligning with the stateless 2026-07-28 revision (no session handshake, `server/discover`) is an open issue. ([issue #437](https://github.com/open-telemetry/semantic-conventions-genai/issues/437))

### Claude Code OpenTelemetry export

Opt-in with `CLAUDE_CODE_ENABLE_TELEMETRY=1`, then `OTEL_METRICS_EXPORTER` (`otlp`/`prometheus`/`console`/`none`) and `OTEL_LOGS_EXPORTER` (`otlp`/`console`/`none`) plus standard `OTEL_EXPORTER_OTLP_*` endpoint/header variables; admins can pin all of this in managed settings. ([monitoring](https://code.claude.com/docs/en/monitoring-usage))

- **Metrics**: `claude_code.session.count`, `lines_of_code.count`, `pull_request.count`, `commit.count`, `cost.usage` (USD), `token.usage`, `code_edit_tool.decision`, `active_time.total`.
- **Events (OTel logs)**: `claude_code.user_prompt`, `assistant_response`, `tool_result`, `tool_decision`, `api_request`, `api_error`. `tool_result` carries `tool_name`, **`tool_use_id` (matches the id passed to hooks, so OTel events join with hook-captured data)**, `success`, `duration_ms`, `error_type`, `decision_type`, `decision_source` (`config`/`hook`/`user_permanent`/`user_temporary`).
- **Correlation**: every event carries `session.id` and `prompt.id` (a UUID tying one user prompt to everything it triggered) plus `event.sequence` for ordering within a process.
- **Redaction by default, one switch per content class**: prompt text is `<REDACTED>` unless `OTEL_LOG_USER_PROMPTS=1`; assistant text unless `OTEL_LOG_ASSISTANT_RESPONSES=1` (falls back to the prompt switch when unset); tool parameters, Bash commands, MCP server/tool names and full error messages unless `OTEL_LOG_TOOL_DETAILS=1`; tool output (on trace spans, truncated at 60 KB) unless `OTEL_LOG_TOOL_CONTENT=1`.
- **Traces (beta)**: `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` + `OTEL_TRACES_EXPORTER`. Root span `claude_code.interaction` per prompt, children `llm_request`, `hook`, and `tool` → `tool.blocked_on_user` (permission wait) / `tool.execution`. A W3C `traceparent` is sent on outbound API and MCP requests and subprocesses inherit `TRACEPARENT`, so a downstream MCP gateway can join the agent's trace.
- **Local retention**: session transcripts are deleted after `cleanupPeriodDays` (default 30). ([settings reference](https://code.claude.com/docs/en/settings-reference))

### Codex CLI telemetry and local logs

OTel is **off by default**, configured in `config.toml`: ([advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced))

```toml
[otel]
environment = "staging"   # default "dev"
exporter = "none"         # or otlp-http / otlp-grpc
log_user_prompt = false   # prompts redacted unless true
```

Events: `codex.conversation_starts` (model, reasoning settings, sandbox/approval policy), `codex.api_request`, `codex.sse_event` (token counts), `codex.user_prompt` (length; content redacted by default), `codex.tool_decision` (approved/denied + source), `codex.tool_result` (duration, success, **and an output snippet** — tool output is not behind a switch, unlike Claude Code). Every event carries `conversation.id`. A separate `trace_exporter` handles spans; third-party write-ups note the span signal never carries prompt/response text or token cost — those only go to the logs exporter. ([SigNoz guide](https://signoz.io/docs/codex-monitoring/)) Local state: `~/.codex/log/codex-tui.log` (verbosity via `RUST_LOG`), rollout files under `~/.codex/sessions/`, and `~/.codex/history.jsonl` bounded by `[history] persistence` / `max_bytes`.

### MCP logging utility (deprecated in 2026-07-28)

Servers declaring the `logging` capability send `notifications/message` with `level` (the eight RFC 5424 syslog levels, debug→emergency), optional `logger` name and arbitrary JSON `data`; clients set a floor with `logging/setLevel`. Servers SHOULD rate-limit; log messages **MUST NOT contain credentials, secrets or PII**; clients MAY display, filter, search and persist them. ([2025-11-25 logging](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/logging)) The 2026-07-28 revision **deprecates Logging** (with Roots and Sampling); it keeps working for at least twelve months. ([2026-07-28 release post](https://blog.modelcontextprotocol.io/posts/2026-07-28/)) The practical consequence: server-side log streams are not a durable foundation for a gateway's call log; OTel spans are the direction.

### MCP Inspector

The official debugging client (`npx @modelcontextprotocol/inspector`) now ships as web, CLI and TUI front ends over a shared core; its UI keeps a per-connection history of requests/responses and server notifications. It is a developer console, not a persisted log — nothing survives the session. One cautionary detail: without an OS keychain it writes OAuth secrets and env values to plaintext `~/.mcp-inspector/secrets.json`. ([repo](https://github.com/modelcontextprotocol/inspector))

### Docker MCP Gateway (~1.6k stars, MIT)

`docker mcp gateway run` fronts containerised MCP servers. Security/logging switches, all defaulting **on**: `--log-calls`, `--block-secrets` (scan payloads in both directions for secret-looking strings), `--verify-signatures` (image provenance). ([flag reference](https://github.com/docker/mcp-gateway/blob/main/docs/generator/reference/mcp_gateway_run.md))

- `--log-calls` is a middleware (`LogCallsMiddleware`) that writes to the gateway's log stream `Calling tool <name> with arguments: <summary>` before the call and `Calling tool <name> took: <duration>` after — **arguments are logged (summarised), results are not**, and nothing is persisted as a queryable table. ([log_calls.go](https://github.com/docker/mcp-gateway/blob/main/pkg/interceptors/log_calls.go))
- Separately, an OTel path records per call a span with `mcp.server.name`, `mcp.server.type`, `mcp.server.image`, `mcp.tool.name`, `mcp.client.name`, a tool-call counter, a duration histogram (ms) and an error recorder — **no arguments on the span**. ([handlers.go](https://github.com/docker/mcp-gateway/blob/main/pkg/gateway/handlers.go))
- **Interceptors** extend this: `--interceptor=when:type:target` with `when` ∈ `before`/`after`/`around` and `type` ∈ `exec`/`docker`/`http`, so users can pipe each call to their own logger or blocker. ([interceptors package](https://pkg.go.dev/github.com/docker/mcp-gateway/pkg/interceptors))

---

## 3. Admin audit logs (the configuration-change reference)

### GitHub audit log

**Record.** Event names are `category.operation` (`repo.create`, `team.add_member`); each entry has action, actor, affected user, org/repo, country (`actor_location.country_code`), `created_at` (epoch ms), SAML/SCIM identity, authentication method, and a per-event `data` object; entries made with a token can be traced to that token. ([enterprise audit log](https://docs.github.com/en/enterprise-cloud@latest/admin/monitoring-activity-in-your-enterprise/reviewing-audit-logs-for-your-enterprise/about-the-audit-log-for-your-enterprise))

**Search UX.** A single qualifier query language in one search box: `action:`, `actor:`, `user:`, `operation:` (access/create/modify/remove/restore/transfer), `repo:`, `created:` with ISO8601 ranges and `>=`/`<=`, `country:`. ([org audit log](https://docs.github.com/en/organizations/keeping-your-organization-secure/managing-security-settings-for-your-organization/reviewing-the-audit-log-for-your-organization))

**Retention.** **180 days** in the UI/API, but **Git events only 7 days** — high-volume event classes get a shorter window than config changes.

**Export and streaming.** JSON/CSV export (capped at 100 MB compressed or 10 minutes). Enterprise streaming to S3, Azure Blob/Event Hubs, Datadog, GCS, Splunk, Purview with **at-least-once delivery** (consumers must dedupe). If the stream pauses, GitHub buffers **7 days**; a pause longer than that resumes from one week ago; beyond three weeks data is lost and streaming restarts at "now". Daily health checks email owners about misconfiguration. API-request events are opt-in and limited to security-relevant endpoints. ([streaming](https://docs.github.com/en/enterprise-cloud@latest/admin/monitoring-activity-in-your-enterprise/reviewing-audit-logs-for-your-enterprise/streaming-the-audit-log-for-your-enterprise))

### 1Password Events API

Three separate streams rather than one mixed log: `/api/v2/auditevents` (admin actions), `/api/v2/itemusages` (item reveal / secure-copy / fill / export / share, with vault and item UUIDs, client app, OS, IP, location), `/api/v2/signinattempts`. Tokens are scoped per stream and `/api/v2/auth/introspect` reports what a token may read. **Secret field values are never in any event** — usage is recorded, content is not. Pagination is a **persistent cursor**: first call sends a `ResetCursor` with `start_time`, every response returns `cursor` + `has_more`, and the cursor stays valid across sessions, so a consumer resumes exactly where it stopped. ([Events API reference](https://www.1password.dev/events-api/reference/))

### Tailscale configuration audit log

Each entry: **actor** (user or Tailscale service), **action** ("approve device", "modify policy file"), **target** (device/user/tailnet), and a **diff** of old and new values — policy-file edits carry the full diff. Filter by time range, action, actor. **Fixed 90-day retention, not configurable**, on **all plans**; API export via a `logs:configuration:read` scope; SIEM/object-storage streaming (Splunk, Datadog, Elastic, S3, GCS, Azure, Vector…) on Premium/Enterprise with configurable upload period (1 min–24 h) and compression. ([audit logging](https://tailscale.com/kb/1203/audit-logging), [log streaming](https://tailscale.com/kb/1255/log-streaming))

### Cloudflare Audit Logs v2 (GA 2026-03)

Generated **automatically from the API layer**: the audit record is derived from each product's OpenAPI schema, which is how v2 reaches ~95% of products without per-product audit code. Record shape: `action` {description, result, time, type ∈ create/update/delete/view}, `actor` {id, email, ip_address, type ∈ user/account/cloudflare_admin/delegated_service/system, context ∈ api/api_token/dash/oauth/…}, `raw` {method, uri, status_code, Ray ID}, `resource` {id, type, product, scope ∈ user/account/zone, request, response}. Retention **18 months**, but the dashboard queries only 90 days; the full window is via API or Logpush. Sensitive GET reads are not yet logged. ([audit logs v2](https://developers.cloudflare.com/fundamentals/account/account-security/audit-logs/), [GA changelog](https://developers.cloudflare.com/changelog/post/2026-03-10-audit-logs-v2-ga/))

---

## Summary table

| Product | Config audit log | Tool/LLM call record | Payload default | Retention default | Correlation | Export |
|---|---|---|---|---|---|---|
| Langfuse | Enterprise only; actor + before/after JSON | trace → nested observations | captured; client mask hook | self-host ∞; Cloud 30 d–3 y; nightly sweep | trace id, session id | UI export, API |
| Phoenix | — | OpenInference spans | captured; `HIDE_*` env | ∞; days or trace-count, per-project cron | trace, session | API |
| LangSmith | Enterprise; OCSF, writes only, 400 d | runs with `dotted_order` | captured; `HIDE_*` env | 14 d base; SaaS max 180 d | trace, thread metadata | API |
| Helicone | — | proxied request rows | captured; omit headers | 7 d free | session id + path headers | API |
| AgentOps | — | session → agent → op → llm/tool | captured | event-capped free; unlimited paid | session | paid export |
| OTel GenAI/MCP | — | spans + duration metrics | **opt-in** args/results | n/a | W3C trace context in `_meta` | OTLP |
| Claude Code | — | `tool_result` events, beta spans | **redacted**, 4 switches | transcripts 30 d | session.id, prompt.id, tool_use_id | OTLP/Prometheus |
| Codex | — | `codex.tool_result` | prompts redacted; output snippet kept | history `max_bytes` | conversation.id | OTLP |
| Docker MCP GW | — | log line + OTel span | args summarised in log, not on span | n/a (stderr) | span context | OTLP, interceptors |
| GitHub | action/actor/data | — | n/a | 180 d; Git 7 d | actor, token | JSON/CSV, streaming |
| 1Password | separate audit/usage/sign-in streams | item usage | secrets never logged | — | persistent cursor | Events API |
| Tailscale | actor/action/target/diff | — | n/a | 90 d fixed, all plans | — | API, streaming |
| Cloudflare v2 | auto from OpenAPI | — | request/response per action | 18 mo (90 d in UI) | Ray ID | API, Logpush |

---

## Patterns and trade-offs

- **Three distinct records, not one.** Mature products keep configuration audit (low volume, long retention, actor + diff), usage/invocation events (high volume, short retention, no content) and diagnostic logs (free text) as separate stores with separate retention. 1Password even splits usage from audit at the API level; GitHub gives Git events 7 days against 180 for everything else; Langfuse and LangSmith exempt audit logs from trace retention.
- **Actor + action + target + diff is the consensus audit shape.** Tailscale and Langfuse store old/new values; Cloudflare adds actor *type* and *context* (dashboard vs API token vs system) so automated changes are distinguishable from human ones. `category.operation` naming (GitHub) and create/update/delete/view action types (Cloudflare) keep filters simple.
- **Content off by default is where standards landed; platforms still capture by default.** OTel makes tool arguments/results opt-in, Claude Code redacts prompts, tool details and output behind four separate switches, 1Password never logs secret values. The commercial observability platforms (Langfuse, Phoenix, LangSmith, AgentOps) capture everything and offer a hide/mask escape hatch. Codex and Docker's log line sit in between (tool output snippet / argument summary kept). The split tracks the audience: debugging tools want payloads; security and admin logs don't.
- **Redact per content class, not all-or-nothing.** Claude Code distinguishes prompts, responses, tool parameters/names and tool output; OpenInference distinguishes values from message arrays. Metadata (tool name, duration, success, error class) stays visible in every case.
- **Retention is a scheduled sweep with a floor.** Nightly (Langfuse), per-policy cron (Phoenix) or fixed windows (Tailscale 90 d, GitHub 180 d, Cloudflare 18 mo). Self-hosted defaults lean indefinite (Langfuse, Phoenix); SaaS defaults are fixed and short. Count-based caps (Phoenix) bound disk use for bursty workloads where age-based caps don't.
- **Correlation comes from ids minted upstream and carried through.** W3C `traceparent` in MCP `_meta` (OTel) and on outbound MCP requests (Claude Code); `prompt.id` and `tool_use_id` (Claude Code) to join events with hooks; session/thread ids that must reach every child (LangSmith warns filtering breaks otherwise). OTel's rule not to invent a conversation id when none exists avoids false joins.
- **Tree reconstruction is a data-model decision.** LangSmith's `dotted_order` makes the tree and time order one sortable string; Helicone encodes hierarchy in a header path; OTel uses parent span ids.
- **Governance is the paywall line.** Langfuse and LangSmith both put audit logs, retention policy and server-side masking in Enterprise; Tailscale is the exception with audit on every plan (streaming is paid).
- **Export is either a cursor or a stream.** 1Password's resumable cursor and GitHub's at-least-once streaming with a bounded buffer are the two proven models; OCSF (LangSmith) is the emerging interchange schema for SIEM ingestion.

## Worth borrowing / worth avoiding

**Worth borrowing**
- Separate audit, invocation and diagnostic records with separate retention windows, and exempt the audit record from the aggressive sweeps applied to high-volume data.
- Record old/new values on configuration updates (Tailscale, Langfuse) and an actor *type* (human via UI, API token, system/automation) next to the actor id (Cloudflare).
- Model an invocation row on the OTel MCP span: method, tool name, server, session id, JSON-RPC request id, duration, status, `error.type` — and treat arguments/results as a separate, off-by-default opt-in with a truncation limit (Claude Code's 60 KB).
- Accept and emit W3C trace context through `params._meta`, and keep agent-supplied ids (`prompt.id`, `tool_use_id`, `conversation.id`) as correlation columns so a gateway record can be joined to the agent's own OTel stream.
- Offer both age-based and count-based retention with a visible schedule (Phoenix), and clean up orphaned parents (empty sessions) after a sweep.
- A single qualifier search box (`actor:`, `action:`, `created:>=`) as the filter UX (GitHub), plus a thread/timeline view that shows one conversation's turns with drill-down to a single call (LangSmith's Trajectory/Details).
- For export, a persistent resumable cursor (1Password) is simpler and more robust for a local consumer than push streaming; JSON Lines with an OCSF-shaped mapping keeps SIEM ingestion open.

**Worth avoiding**
- Logging arguments by default in free-text logs (Docker MCP Gateway's `Calling tool … with arguments`) — the diagnostic log becomes the leak even when the structured record is clean. The MCP spec's rule that logs must not carry credentials or PII applies to the gateway's own logs too.
- "Omit" switches that still ship the payload through the backend (Helicone) — redaction should happen before the data leaves the process that holds it.
- Indefinite retention as the silent default (Langfuse and Phoenix self-host); unbounded tables surface later as disk and query-time problems.
- Building on MCP server log notifications as a long-term channel — deprecated in 2026-07-28.
- Generating synthetic conversation/session ids when none exists (OTel explicitly forbids it) — it creates plausible-looking but false correlations.
- Relying on a trace id that is not propagated to every child record (LangSmith's warning) — thread views and aggregates silently undercount.
