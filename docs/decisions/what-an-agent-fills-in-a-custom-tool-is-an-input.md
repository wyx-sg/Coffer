# What an Agent Fills in a Custom Tool Is an Input; Query Parameters Are Only the URL's

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [A Custom Tool's Test and a Group's Environments Each Have Their Own Tab](custom-tool-pages-give-testing-and-environments-their-own-tabs.md), [Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md), spec web-ui "Manage custom tool groups on their own page"

## Context

The custom tool editor had a tab called **Arguments** (参数) for the values an
agent fills when it calls the tool, and on the Request tab a field called
**Query** (查询参数) for the URL's `?a=b` pairs. In Chinese both read as
"parameters", so the maintainer could not tell why there were two. The two
are different things: an argument is an input in the tool's schema; a query
pair is part of the request, and its value may be a fixed text or `{name}`,
an argument's value.

How comparable products name them: Postman, Insomnia, Bruno and Hoppscotch
use **Params** / **Query** only for the URL's query string and call values
filled from elsewhere variables (`{{var}}`). n8n's HTTP Request Tool calls the
`{placeholder}`s an AI fills **Placeholder Definitions**. Dify calls them the
tool's **parameters**, but its HTTP details live in an OpenAPI schema, so no
query field shares the word.

## Options Considered

### Option A — Inputs, and "URL query parameters" (chosen)

The tab is **Inputs** (输入): what the agent fills, placed in the request as
`{name}`. The query field is **Query parameters** (URL 查询参数) with a
"Filled by" column; a pair filled by an input shows the chip **Input · name**,
which opens that input's row. Pros: no shared word; "input" is what the MCP
tool's `inputSchema` calls them, which is what an agent sees. Cons: the API
and the tool schema still say `arguments`; the word changes only in the UI and
docs.

### Option B — Keep "Arguments", rename only the query field

Loses because 参数 is still in both labels in Chinese ("查询参数" vs "参数"),
which was the complaint.

### Option C — "Placeholders", like n8n

Loses because a placeholder names the `{name}` mark, not the value; an input
also carries a type, a description for the agent and whether it is required,
and is sent as JSON when no body template uses it.

## Decision

In the web UI and docs, what an agent fills is an **input** (输入);
**query parameters** are only the URL's. Wire formats, the API and the tool's
JSON schema keep `arguments`, because agents already see them
([Names Visible to Agents Are Fixed](names-visible-to-agents-are-fixed.md)).

## Consequences

The i18n keys under `customTools.editor`, `import` and `test` say input; a new
string about these values uses the same word. A query or header value filled
by an input names the input.
