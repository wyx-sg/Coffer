# Tool Search Indexes Parameter Text

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [Tool Overload: List a Usage-Ranked Slice, Search the Rest](tool-overload-tier-the-list-search-the-rest.md), [Tool Search Cuts CJK Text Into Bigrams](tool-search-cuts-cjk-text-into-bigrams.md), [Eval Capture and Regression Gate](eval-capture-and-regression-gate.md), spec mcp-gateway "Forward tools, resources and prompts"

## Context

`coffer__search_tools` scored a tool's name (weight 3.0) and description
(1.0) only. Part of a tool's meaning often lives in its input schema instead.
On the owner's catalogue, "find a user by phone number" ranked
`postman__getTeamUser` and two other `user`-named tools above the account
lookup that takes a `phone_list` parameter: `user` in a name, at three times
the weight, beat a description that never says "phone". Enum values carry
meaning the same way (an order list whose `order_status` takes `SHIPPED`).

How comparable tool-search features treat the schema:

- **Anthropic's tool search tool** (regex and BM25 variants) searches "tool
  names, descriptions, argument names, and argument descriptions".
- **FastMCP's tool-search transforms** (regex and BM25) search the same four
  fields.

## Options Considered

### Option A — Parameter names, descriptions and enum values, light weight, outside the length (chosen)

Each property's name (split on `_` and case like any other text), its
description and its string enum values, walking nested objects and array
items, form a third text at weight 0.5. These terms add to a tool's score but
not to its length in BM25's length normalisation.

- Pros: matches what Anthropic and FastMCP index; finds tools whose intent is
  only in the schema; keeps the name and description in charge.
- Cons: a large schema adds many terms, so a common word (`id`, `page`) can
  touch many tools, though its idf keeps that small.
- Why outside the length: length normalisation exists to stop a verbose
  description outscoring a short exact one. A tool with fifteen parameters is
  well described, not verbose; counting its schema pushed its name and
  description matches down. On the eval, with the schema counted in the
  length, adding parameter text left MRR worse than leaving it out (0.595
  against 0.603); outside the length it rose to 0.633, and recall@5 to 0.787.

### Option B — Names and descriptions only (the previous design)

- Pros: simplest; no schema walk.
- Cons: misses schema-only intent, as above.
- Loses: recall@5 0.753 and MRR 0.603 on the same eval, below Option A.

### Option C — Parameter names only, or names and enums

The TODO that raised this suggested names and enum values.

- Pros: smaller text than including descriptions.
- Cons: parameter descriptions are where Chinese-language tools say what a
  parameter means (`phone_list`: 手机号列表), which names alone cannot match
  in Chinese. Measured lower (with the schema counted in the length): recall@5 0.730 to 0.742 at every weight tried, against 0.775 for the full text.
- Loses on the measurement.

### Option D — Same weight as the description

- Measured at 1.0: recall@5 0.764 and MRR 0.632 (outside the length), no better
  than 0.5 and noisier on long schemas. 0.25 gave 0.764 and 0.625.
- Loses narrowly; 0.5 keeps the schema clearly below the description.

## Decision

The search corpus for each tool is its name (3.0), its description (1.0) and
its input schema's parameter names, parameter descriptions and string enum
values (0.5, any depth up to four levels). Parameter text scores but does not
count toward the document length.

## Consequences

- `schema_text` in `backend/coffer/domain/mcp/tool_search.py` builds the text;
  the gateway and the eval use the same function, so the eval scores what the
  gateway ranks.
- Results keep their shape. Each still carries the full input schema, which
  the agent needs to call the tool without a second round trip (FastMCP does
  the same; Anthropic returns references the API expands for the model).
