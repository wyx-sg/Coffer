# A Custom Tool's Test and a Group's Environments Each Have Their Own Tab

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [What an Agent Fills in a Custom Tool Is an Input](what-an-agent-fills-in-a-custom-tool-is-an-input.md), [A Body Template Is Laid Out by Its Tokens, Never Parsed](a-body-template-is-laid-out-by-its-tokens.md), spec web-ui "Manage custom tool groups on their own page", "Preview and test a custom tool in one chosen environment", OpenSpec change `tidy-custom-tool-pages`

## Context

The custom tool editor was a form with a fixed right-hand column beside it:
the request preview (method, URL, headers, no body), sample values for the
inputs, **Run** and the response. The maintainer found both halves too narrow
to read: a long description or a JSON body wrapped in a few words per line,
the preview's header list and the response's JSON were cramped, and a run's
result pushed the preview out of sight.

A group's page had the same problem one level up. Its Overview stacked the
definition, the environments, the last 24 hours, dependencies and the most
used tools; each environment was one line (name, base URL, secret state), so
its headers, variables and timeout needed **Edit** to read, and comparing
`test` with `live` meant opening two dialogs.

How comparable products lay this out:

| Product | Request and its test | Environments |
| --- | --- | --- |
| Postman | Request on top, response below (or side by side on wide screens); the response has Body / Headers tabs | Its own page, one table: variable, type (default / secret), value |
| Insomnia, Bruno | Request left, response right, each a full column | Bruno: one table per environment with a Secret tick; collection settings are tabs (Headers, Auth, Vars) |
| Hoppscotch | Response below the request | A table per environment, rows marked secret |
| n8n HTTP Request Tool (closest: an HTTP tool an AI calls) | **Test step** runs it, the result full width | — |
| Dify custom tool | A separate **Test** dialog: values, then the result | — |

The API clients treat sending a request as the page's main job, so the
response gets half the screen. The two products built around a tool an AI
calls, which is what Coffer's are, test in a step or view of its own.

## Options Considered

### Option A — Test is the editor's last tab; environments are a tab of the group's, after Overview (chosen)

The editor's tabs are General, Request, Inputs, Response and **Test**, each
full width. Test reads top to bottom: where it runs and **Run**, a sample
value per input, the request a run sends with those values (now including
the body), then the response with Body / Response headers tabs. The tab keeps
its values and result while the person switches tabs, so they can fix the
request and come back.

A group's tabs are Overview, **Environments** and Tools: where its calls go
comes before the tools that use it. Each environment is
a card that shows everything it holds — switch, secret state, base URL,
timeout and whose it is, headers, variables — with **Edit** and a menu for
Delete.

Pros: every view gets the drawer's full width; the request a run sends is
readable in full, body included; environments can be read and compared
without a dialog. Cons: changing the request and seeing its result is a tab
switch apart. That is how n8n and Dify work, and a run's result is kept
across the switch.

### Option B — Keep the side column and tidy it

Lay the preview out as a table and give the response more height, but keep
it beside the form. Loses because the width is the problem: half a drawer
cannot show a JSON body or a long URL without wrapping, whatever the layout
inside it.

### Option C — Request above, response below, Postman style

Make the editor one long page with the test under the request fields. Loses
because the editor is a form for a tool definition, not a request runner:
the inputs and response rules would sit between the request and its result,
and the page would scroll past five sections to reach **Run**.

### Option D — Environments stay in the Overview, expandable

Each environment line opens in place to its details. Loses because the
Overview still stacks five sections, and comparing two environments needs
both open in a long page; a tab of cards shows them side by side in reading
order.

## Decision

The custom tool editor has no side column: testing is its last tab, full
width, and keeps its state while the person moves between tabs. A group's
environments are its own tab of cards that show every setting without
opening them. Every header list — the tool's Request tab, the request a test
sends, an environment's card, a response's headers — is one shared table
(name, value, and where it comes from when rows are inherited).

## Consequences

- `ToolEditorForm` mounts the Test tab once (`forceMount`), so sample values
  and the last result survive tab switches.
- `HeaderTable` is the one component for header lists; a new header surface
  uses it.
- `customToolTabs.ts` lists the group page's tabs; `/custom-tools/<group>/environments`
  is an address.
- Docs screenshots and the Capabilities canvas show the tabs; a change to
  either layout updates both.
