## Why

`coffer__search_tools` drops every character outside `[a-z0-9]`, so a query in
Chinese matches nothing at all: on the owner's 284-tool catalogue, 查询账号列表
returned zero results although the account tools are described in Chinese. It
also never reads the input schema, so a tool whose intent lives in a parameter
(`phone_list` on an account lookup) loses to any tool with `user` in its name.
And the eval that should have caught both had 14 English queries over 22 tools.

## What Changes

- The ranker cuts Chinese, Japanese and Korean text into overlapping character
  pairs (a lone character stays itself), after folding full-width forms, so a
  query in those languages matches descriptions written in them.
- Each tool's input schema contributes a third, lightest-weighted text: its
  parameter names, parameter descriptions and string enum values, nested
  objects and array items included.
- The tool-search eval grows to a catalogue shaped like a real one (public MCP
  servers plus internal services described in Chinese, with input schemas) and
  queries in English, Chinese and both, scored as recall@5 and MRR; the gate
  now holds MRR as well as recall, and the report shows recall on the Chinese
  queries on its own.
- Results are unchanged in shape: each still carries the tool's full input
  schema, which the agent needs to call it.

## Capabilities

### Modified Capabilities

- `mcp-gateway`: "Forward tools, resources and prompts" — the ranker's text and
  tokenization.

## Impact

`backend/coffer/domain/mcp/tool_search.py`,
`backend/coffer/application/mcp/gateway_tool_search.py`, `evals/`, the MCP
gateway architecture page (en/zh), ADRs
[Tool Search Cuts CJK Text Into Bigrams](../../../docs/decisions/tool-search-cuts-cjk-text-into-bigrams.md)
and [Tool Search Indexes Parameter Text](../../../docs/decisions/tool-search-indexes-parameter-text.md),
and [Tool Overload](../../../docs/decisions/tool-overload-tier-the-list-search-the-rest.md).
