# Tool Search Puts an Exact Name First

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: [Tool Overload: List a Usage-Ranked Slice, Search the Rest](tool-overload-tier-the-list-search-the-rest.md), [Tool Search Indexes Parameter Text](tool-search-indexes-parameter-text.md), spec mcp-gateway "Find any tool in the catalogue"

## Context

Agents often call `coffer__search_tools` with a tool's name, not a
description: they saw the name in an error, in a skill, or in an earlier
session. Of the owner's real queries on 2026-11-06, a third were names or held
one (`get_account_list`, `toc-account__get_account_audit_log`,
`seatalk get_thread_by_thread_id`). BM25 scores a name by its tokens, so a
query that is exactly `get_account_audit_log` could rank
`postman__getAuditLogEventActions` above `toc-account__get_account_audit_log`,
whose tokens are shared with its neighbours.

Anthropic's tool search tool and FastMCP's search transforms rank by score
only. Claude Code's own deferred-tool search takes `select:<name>` to fetch a
named tool exactly.

## Options Considered

### Option A — A query that spells a tool's name puts that tool first (chosen)

When the whole query, trimmed and case-folded, equals a tool's full name
(`server__tool`) or the part after `__`, that tool is returned first, ahead of
every scored result, and the rest follow by score. A query with a space is not
a name. A name shared by two servers' tools puts both first, in catalogue
order.

- Pros: an agent that knows the name always gets it at rank 1; nothing changes
  for a description query (the eval's recall@5 0.775 and MRR 0.633 are
  unchanged); a few lines in the ranker.
- Cons: a one-word query that happens to be a tool's bare name (`search`)
  promotes that tool even when the agent meant the word.
- Why it wins: a bare name like `search` is already that tool's strongest
  match by score, so the promotion rarely changes an answer; when it does, the
  agent asked for that name.

### Option B — Score only (the previous design)

- Cons: a name query can lose to a tool with more matching tokens, as above.
- Loses: the agent knew the answer and the search hid it.

### Option C — A separate `select:` syntax or a `name` argument

- Pros: explicit; no ambiguity with a one-word description.
- Cons: the agent must learn a syntax this tool's description would have to
  teach; real queries show agents pass the name as the query already.
- Loses: it fixes the case only for agents that learn the syntax.

## Decision

`rank_tools` returns the tools whose name the query spells exactly first,
then the scored results. A query containing whitespace never matches a name.
The retrieval eval's gate is unchanged and still applies.

## Consequences

- The eval does not measure name queries; a name query is right by
  construction, so a test in `tests/unit/domain/mcp/test_tool_search.py` pins it.
- A change to how names reach the ranker (today `server tool`, the namespace
  split off) must keep the match on both spellings.
