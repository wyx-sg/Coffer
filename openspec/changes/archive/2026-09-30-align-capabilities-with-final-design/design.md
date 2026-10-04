## Context

Three canvas decisions need backend support: testing a server config before it is saved, previewing an import from the agents before anything is written, and showing Coffer's own `coffer` server on the MCP servers page.

## Decisions

### One probe for both tests

The unsaved-config test and the registered-server test run the same probe (`infrastructure/mcp/probe.py`) over the existing `StdioUpstreamConnection` / `HttpUpstreamConnection`, so the Add dialog and the server page read one result shape. The stdio connection gained two options rather than a second spawner: a private stderr sink (the test reads it back; nothing goes to the server's log) and stopping the whole process group on close. The SDK signals the group only when the leader outlives stdin closing, so a leader that exits and leaves a forked grandchild would otherwise leak it. The exit status reaches the result through a `/bin/sh` wrapper that waits for the server and prints it on stderr, because the SDK does not expose the process.

The unsaved test releases no stored secret (a binding is per registered destination and needs approval) and persists nothing. A typed URL passes the SSRF guard; the SDK follows redirects only within the URL's origin.

### The import plan reuses the reconciler's vocabulary

The import plan is not a reconcile target: it is a one-off, person-chosen write, not a state Coffer keeps true. It reuses what the reconciler dry run is made of:

- **The change vocabulary.** Every planned write is a `PlannedChange` — a `Difference` of target `mcp_import` with `Item`s carrying safe JSON text (command, arguments, URL, key names; never a value), and a `Decision` whose reason code (`import_add`, `import_merge`, `import_duplicate`, `import_remove_entry`) says why. The wire renders them with the reconcile routes' own `ReconcileItemOut`, so the plan reads like the drift view's change preview.
- **The pending plan.** `Reconciler.plan(targets=["mcp_entry"])` — pure, it writes nothing — supplies any difference already pending on Coffer's own entry for the agents involved, because that entry is how they will reach what they import. Apply performs the repairable ones through `Reconciler.apply` first.

What the reconciler has no answer for is added beside it: the per-file unified-diff hunks (`domain/agent/config_diff.py`, `difflib` with three lines of context), computed against the file's real text and the text `mcp_entries.remove_entry` would write, with every shown line redacted — context lines included, since another entry's token can sit there. Apply recomputes the plan and performs each write through the path that already owns and audits it: `AgentMcpEntryService.adopt` for a new server, `remove_entry` for merged and duplicate entries, `ResourceService.update_scope` for reach.

### The built-in server is described, not registered

`GET /api/v1/mcp/builtin` builds the `coffer` server from the gateway's built-in tool list, the bound port, the connected agents and the invocation log's reserved uid `coffer`. A fake `mcp_server` row would be listed, edited and synced like any other; there is nothing about it a person can change. Which agents are connected is the agent kind's knowledge, so the composition root hands the MCP route a callable over it.
