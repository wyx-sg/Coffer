# One Hand-Off per MCP Server or Custom Tool Group, Carrying the Real Error

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: spec mcp-gateway "Hand a failing MCP server's diagnosis to an agent", "Name a missing stdio launcher", "Hand a failing custom tool group to an agent", "Name why an upstream failed in Coffer's words", "Explain a server's state on its page"; spec web-ui "Hand an environment failure on Activity to an agent"

## Context

A failing MCP server had four hand-off prompts, each written by its own
function: a missing launcher, a failing server, a single failed call (on its
Activity record), and a failing custom tool group (plus a fifth for a group's
failed test). The server page also derived several facts about the failure:
when the last error happened, since when the server had been failing, and
which tool the last success called. Meanwhile the error every prompt quoted was
the exception's class name (`MCPError`, `ConnectError`), so none of them said
what was wrong.

Comparable tools hand over the error itself: GitHub Actions' "Explain error"
and Sentry's issue summaries take one failure with its message and context;
none offers a separate prompt per occurrence.

## Options Considered

### Option A — One prompt per server and one per group, with the real error (chosen)

A server's hand-off is one function: it asks to install the launcher when that
is the cause, otherwise to find the cause, and always quotes the newest error
in Coffer's words (the network failure's kind, the HTTP status, or a stdio
server's exit with its last stderr line). A group's tests and its failing state
share one function too. A single call has no hand-off: its record names the
failure and links to the server page, where the server's hand-off is.

- Pros: one prompt to maintain per kind, and the same words on the page, the
  test result and Overview; the prompt finally says what failed.
- Cons: the per-call prompt's call id and session are not handed over; the
  agent finds them with `coffer log mcp` if it needs them.

### Option B — Keep the four prompts and add the real error to each

- Cons: four functions saying nearly the same thing, which drift; the per-call
  prompt duplicates the server's on every failed row.

### Option C — Drop the prompts; let the person paste the error

- Cons: the prompt is what makes the hand-off safe (no secret, the machine, the
  config summary, the verification step). Losing it loses that.

## Decision

Option A. The server status read keeps the last error, the time of the last
success, when the health record was written, the missing launcher, the missing
secret and the "requires" list; it drops the last error's time, the
failing-since time and the last successful tool.

## Consequences

- `InvocationOut.handoff` is gone; the Activity drawer's footer opens the
  server, and a daemon ERROR about the environment keeps its hand-off.
- The Overview's MCP items carry the server's hand-off with its newest error.
