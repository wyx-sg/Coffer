# A Tool Response Reaches the Agent as the Upstream Sent It

**Status**: Accepted
**Date**: 2026-11-10
**Deciders**: Yuxing Wu
**Related**: [Only the Person Answers a Secret's Approval, and Only in the App](only-the-person-answers-a-secret-approval-in-the-app.md), spec mcp-gateway (custom tools' response rules)

## Context

On 2026-10-29 an agent that built the `toc-account-write` custom tool group
switched its change-password tool off and wrote "BLOCKED: keep this tool
disabled until Coffer can project the upstream response to reviewed safe
fields", because the API answers with a fresh login token. Coffer has no such
feature. On 2026-11-10 another agent read that note and refused the tool until
the owner switched it on by hand; it then ran it through a script that printed
only the fields it needed.

The question: should Coffer filter what a tool returns (keep or drop fields, or
mask anything that looks like a credential) so a sensitive value never reaches
the agent?

How comparable products handle it (2026-11):

- **API gateways** (Kong response-transformer, Azure API Management `set-body`)
  and some MCP gateways (Gravitee, mcp-gateway transforms) let an operator
  configure which response fields pass.
- **Docker MCP Gateway** (`--block-secrets` interceptor), Lasso and similar
  scanners match tool output against secret patterns and block or mask it.
- **OpenAI and Anthropic tool calling**: the application decides what it hands
  back; the platform does not filter.

## Options Considered

### Option A — Pass the response through; tell agents to call the tool (chosen)

Coffer returns what the upstream answered, as the developer configured the tool
(response rules still say whether a call succeeded). The coffer-guide skill says
a sensitive response is no reason to refuse, disable or postpone a tool, and not
to repeat a credential in a reply, a file or a memory.

- Pros: nothing to build; the developer who gave the agent the tool already
  decided it may see the answer. Matches the lean principle: an agent that
  wants less can print only what it needs.
- Cons: a token the upstream returns enters the agent's context.

### Option B — Per-tool response field filter

An allow-list or deny-list of JSON Pointers per tool, applied before the result
leaves Coffer.

- Pros: the value never reaches the agent.
- Cons: a new config field, editor UI, docs and canvases for one tool today;
  the owner had already declined response trimming in the 2026-11-06 MCP review.

### Option C — Mask anything that looks like a secret

Run the bundled gitleaks rules over every response.

- Pros: no per-tool setup.
- Cons: an opaque login token often matches no rule, while a false positive
  hides a value the agent needs; the outcome is unpredictable.

## Decision

Option A. Option B is the path if a real case needs a value kept from the agent;
it is not built now.

## Consequences

- Agents stop treating a sensitive response as a blocker.
- A tool description written by an agent that claims Coffer will filter
  responses is wrong and should be edited.
