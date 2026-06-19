# Competitive Research — Observability, Audit & Governance + MCP Security

> English: this file · 中文版: [observability-governance.zh.md](./observability-governance.zh.md)
>
> Internal competitive-research report for Coffer's audit/retention/invocation
> log + local security primitives. **Date:** 2026-06-16. **Method:** deep-research
> harness (key findings 3-0 confirmed).

## 1. Landscape at a glance

This space splits into two angles Coffer straddles partially:

| Angle                             | What it is                                        | Examples                                                                                    |
| --------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **(A) Agent/LLM observability**   | Trace model+tool calls, tokens, cost, latency     | Langfuse, LangSmith, Helicone, Arize Phoenix, AgentOps; **OpenTelemetry GenAI conventions** |
| **(B) MCP security / governance** | Detect tool poisoning, rug-pull, prompt injection | Invariant `mcp-scan`, Lasso MCP Gateway, Prompt Security                                    |

### (A) Observability

- **Langfuse** (MIT, free self-host via Docker Compose / Kubernetes) — captures
  agent traces/graphs, session/thread + user tracking, and **token + cost
  tracking on all tiers including the free Hobby tier**. Notably, it **gates
  audit logs / SSO / RBAC behind Enterprise** — i.e. the _governance_ surface is
  paywalled.
- **OpenTelemetry GenAI semantic conventions** — the emerging vendor-neutral
  standard: `gen_ai.operation.name` (`create_agent` / `invoke_agent` / `plan` /
  `execute_tool` / memory ops), standardized token usage (input/output + cache-
  creation / cache-read / reasoning sub-categories), latency, finish-reasons,
  duration/token histograms, and tool-call attributes. **Full prompt/arg/result
  content is Opt-In (the lowest requirement level) and OFF by default for
  privacy.** ⚠ Still at **"Development" maturity — NOT GA**; attribute names can
  change without a major version bump; recently relocated to a dedicated
  `open-telemetry/semantic-conventions-genai` repo. [confirmed 3-0]

### (B) MCP security

- **Invariant Labs `mcp-scan`** (Apache-2.0, **acquired by Snyk**) — detects
  **prompt injection in tool descriptions** and **tool poisoning**; implements
  **Tool Pinning** (hashes tool definitions to catch **rug-pull / silent
  redefinition**); runs static ("scan") or runtime ("proxy"/gateway) mode.
- **Lasso MCP Gateway** (OSS) — proxy + orchestrator applying configurable
  request/response filters, **secret masking**, and server/tool-description
  scanning.
- **Prompt Security** (**acquired by SentinelOne**) — runtime prompt-injection /
  output-manipulation / model-abuse defense + an MCP gateway.
- **Research:** arXiv 2506.01333 (ETDI) attributes these threats to MCP's lack of
  **verifiable authenticity/integrity markers on tool definitions** — exactly
  what Tool Pinning patches.

> **Signal: the MCP-security space is consolidating into security majors** —
> mcp-scan → Snyk, Prompt Security → SentinelOne.

## 2. Capability comparison

| Capability                             | Langfuse         | OTel GenAI           | mcp-scan            | Lasso GW | **Coffer**                                                           |
| -------------------------------------- | ---------------- | -------------------- | ------------------- | -------- | -------------------------------------------------------------------- |
| Model token/cost/latency tracing       | ✅               | ✅ (std)             | —                   | —        | **❌ none**                                                          |
| Agent/tool span tracing                | ✅               | ✅ vocab             | —                   | —        | partial (invocation log)                                             |
| **Mandatory audit log**                | Enterprise-gated | —                    | —                   | —        | **✅ free, actor-tagged, every lifecycle change**                    |
| Retention policies                     | tiered           | —                    | —                   | —        | **✅ central prunable-table registry**                               |
| Invocation record (who/when/outcome)   | ✅               | ✅                   | —                   | —        | **✅ NO args/results (invariant)**                                   |
| Arg/result capture                     | ✅               | opt-in (off default) | —                   | —        | **❌ (no opt-in escape hatch)**                                      |
| Request correlation                    | ✅               | ✅ trace IDs         | —                   | —        | **✅ X-Coffer-Trace**                                                |
| Tool-definition integrity / pinning    | —                | —                    | **✅ hash pinning** | partial  | **❌**                                                               |
| Tool-poisoning / prompt-injection scan | —                | —                    | **✅**              | ✅       | **❌**                                                               |
| Secret masking / rejection             | —                | —                    | —                   | ✅ mask  | **✅ config secret-pattern rejection**                               |
| Local security primitives              | —                | —                    | —                   | —        | **✅ loopback-only, ciphertext creds, signed callbacks, SSRF guard** |
| Self-host / OSS                        | ✅ MIT           | ✅                   | ✅ Apache           | ✅       | ✅                                                                   |

## 3. How Coffer compares

**Where Coffer is competitive or ahead.**

1. **Governance/audit is first-class and free.** A mandatory, actor-tagged audit
   log of every resource lifecycle change + retention policies is _stronger_ than
   the observability leaders here — Langfuse paywalls audit logs behind
   Enterprise; Coffer ships it by default. For a single-user vault this is exactly
   the right emphasis.
2. **The "no arg/result capture" invariant is on the right side of the privacy
   default.** OTel makes content capture opt-in and off-by-default _for privacy_ —
   Coffer enforces the same default as a hard invariant. Alignment, not a gap.
3. **Local security primitives have no analog in the observability tools** —
   loopback-only binding, ciphertext-only credentials, signed channel callbacks,
   SSRF-guarded egress, and config secret-pattern rejection are a coherent
   local-first security posture these cloud tools don't address.

**Where Coffer lags — concrete borrows.**

1. **No MCP tool-definition integrity / Tool Pinning (headline security borrow).**
   mcp-scan hashes tool definitions to detect rug-pull / silent redefinition and
   scans tool descriptions for prompt injection / poisoning. Coffer **aggregates
   upstream MCP servers and already live-queries their capabilities (ADR-004)** —
   it is perfectly positioned to hash + pin tool definitions at the gateway and
   alert on drift. This is the single most on-mission security feature to add.
2. **No opt-in arg/result capture for debugging.** The invariant is right as a
   _default_, but every debugging workflow needs an escape hatch. Borrow OTel's
   model: opt-in, off-by-default, local-only arg/result capture.
3. **No LLM-layer observability.** Coffer doesn't trace its internal model
   (ADR-024) calls — token/cost/latency. If/when it adds tracing, **adopt the
   OpenTelemetry GenAI conventions** (while noting they are still Development, not
   GA).
4. **No runtime policy/guardrail engine.** Lasso/Prompt Security enforce
   request/response filters; Coffer has primitives but no policy layer.

## 4. Key takeaways for Coffer

1. **Lead with governance/audit as a strength** — mandatory free audit +
   retention beats the observability leaders (who paywall audit). For a vault,
   accountability is the right headline.
2. **Add MCP tool-definition pinning (mcp-scan style)** — hash + pin upstream
   tool definitions at the gateway, alert on rug-pull/silent-redefinition, scan
   tool descriptions for injection. Your gateway + ADR-004 capability tracking
   make this a natural, high-value addition; the threat is real and consolidating
   (Snyk/SentinelOne).
3. **Add opt-in, off-by-default arg/result capture** for debugging (OTel content-
   capture model) — keeps the privacy invariant as the default while unblocking
   debugging.
4. **If you add model-call tracing, use the OpenTelemetry GenAI conventions** —
   but treat them as a developing (non-GA) standard.

## 5. Sources

Observability:

- github.com/open-telemetry/semantic-conventions-genai · opentelemetry.io/blog/2026/genai-observability/ · opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans (redirected)
- langfuse.com (self-host, pricing, tracing) · langsmith / helicone / arize phoenix / agentops docs

MCP security:

- github.com/invariantlabs-ai/mcp-scan (Tool Pinning; Snyk acquisition) · lasso.security (MCP Gateway) · prompt.security (SentinelOne acquisition)
- arXiv 2506.01333 (ETDI — tool-definition integrity)

## Verification update (2026-06-19)

> All five primary claims (1 local + 4 web) are **confirmed** against primary
> sources; one minor wording nuance on the local "mandatory" framing remains
> open.

### ✅ Confirmed

- **Coffer's free, payload-free invocation log.** The `MCPInvocation` domain
  model is explicitly documented "NEVER carries args or result content"; its
  fields are timestamp / resource_name / capability_type / capability_key /
  duration_ms / status / error_message / session_id — no args/result columns,
  and the persistence model mirrors this. `repo:backend/coffer/domain/mcp/capability.py:57-69` · `repo:backend/coffer/infrastructure/mcp/invocation_writer.py:32-49`
- **Free, actor-tagged audit log.** `AuditService`/`AuditEntry` record
  actor-tagged lifecycle events (event_type, resource_kind/name, actor, details)
  with no tier gating in code — i.e. free in the self-hosted product. `repo:backend/coffer/application/audit_service.py:13-58`
- **Langfuse paywalls the governance surface.** Audit-log viewer is an
  Enterprise Edition feature; fine-grained project-level RBAC needs an Enterprise
  license key; SSO/SCIM + advanced audit logging sit in Enterprise (SSO also via
  a paid Teams add-on). Pricing: Hobby $0 / Core $29 / Pro $199 / Enterprise
  custom (~$2,499+). https://langfuse.com/docs/administration/audit-logs · https://github.com/orgs/langfuse/discussions/8147
- **OTel GenAI conventions are still "Development" (not GA) and relocated.** The
  new repo's `gen-ai-agent-spans.md` carries "Status: Development" at document
  and per-span level (Create agent, Invoke agent, Invoke workflow, Plan, Execute
  tool); the legacy `opentelemetry.io/docs/specs/semconv/gen-ai/` page now reads
  "moved … no longer maintained." https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md · https://opentelemetry.io/docs/specs/semconv/gen-ai/
- **Both acquisitions closed.** Snyk announced acquiring Invariant Labs
  (mcp-scan makers) in June 2025; mcp-scan stays open-source under Snyk Agent
  Scan. SentinelOne completed its Prompt Security acquisition on 2025-09-05
  (~$180M, announced Aug 5 2025). https://snyk.io/news/snyk-acquires-invariant-labs-to-accelerate-agentic-ai-security-innovation/ · https://investors.sentinelone.com/press-releases/news-details/2025/SentinelOne-to-Acquire-Prompt-Security-to-Advance-GenAI-Security-and-Agent-Security-Strategy/default.aspx
- **mcp-scan Tool Pinning catches rug-pulls.** It hashes each tool's definition
  (name, description, input schema from the `tools/list` manifest) on first scan
  and compares on subsequent scans; any delta alerts — directly targeting tools
  silently redefined after one-time approval. https://invariantlabs.ai/blog/introducing-mcp-scan · https://github.com/invariantlabs-ai/mcp-scan

### ❓ Still uncertain

- **The log being "mandatory" / non-disableable.** The "free" and "payload-free"
  properties are confirmed in code (payload-free is a hard domain invariant per
  the docstring), but no code was found enforcing that recording itself cannot be
  disabled (no opt-out toggle or config gate observed). The "mandatory" framing
  is thus mildly aspirational vs. directly confirmable code. `repo:backend/coffer/infrastructure/mcp/invocation_writer.py:139-152`
