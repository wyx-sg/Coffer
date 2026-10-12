# A Body Template Is Laid Out by Its Tokens, Never Parsed

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [A Custom Tool's Test and a Group's Environments Each Have Their Own Tab](custom-tool-pages-give-testing-and-environments-their-own-tabs.md), spec web-ui "Manage custom tool groups on their own page", spec mcp-gateway "Make a custom tool's request in the gateway"

## Context

A custom tool's body template is JSON with holes: `{name}` outside a string
becomes the input's JSON value, inside a string its escaped text, and
`{env:NAME}` an environment variable. A template like
`{"ids": {userid_list}, "limit": 50}` is not valid JSON, so it cannot be
pretty-printed with `JSON.parse` / `JSON.stringify`. Imported templates were
often one long line, and the editor showed them in a plain text box. The
maintainer asked for JSON laid out readably, as Postman (**Beautify**),
Hoppscotch (**Prettify**) and Bruno do.

## Options Considered

### Option A — Re-indent the template's tokens; check it on a same-length mask (chosen)

`lib/customTools/bodyTemplate.ts` splits the text into strings, holes and
single characters and re-indents by brackets and commas, copying every value
as written. To tell the person where a template is broken, each hole is
replaced by `0`s of its own length and the result goes to `JSON.parse`; its
error position is the template's. Pros: number precision, key order and
spacing inside strings are kept; a hole is never an error; a broken template
is left alone and named by line and column. Cons: a small tokenizer to keep.

### Option B — Swap holes for placeholders, parse, stringify, swap back

Loses because `JSON.parse` rounds large integers and drops duplicate keys, so
**Format** could change what is sent; and a placeholder string changes the
hole's meaning (outside vs inside a string).

### Option C — No formatter, only syntax colouring

Loses because the one-line imported templates stay unreadable, which was the
complaint.

## Decision

The body is a code editor with JSON colouring and holes marked. A one-line
template opens laid out; **Format** lays out any template that checks. Layout
only changes whitespace outside strings, so what the gateway sends is the
same before and after. The preview fills a template by the gateway's rules
(`fillBodyTemplate`), so it shows what a run sends.

## Consequences

`bodyTemplate.ts` and `sentRequest.ts` mirror `backend/coffer/domain/mcp/http_api_render.py`;
a change to the gateway's hole rules changes them in the same PR.
