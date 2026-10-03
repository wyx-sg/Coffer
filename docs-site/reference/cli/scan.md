---
title: coffer scan
description: "List what agents hold that Coffer does not manage: agents, skills, MCP entries."
pageClass: cli-ref
---

# coffer scan

List what agents hold that Coffer does not manage: agents, skills, MCP entries.

```sh
coffer scan [OPTIONS]
```

This page matches what `coffer scan --help` prints. Add `--help` to any command below to see its options in the terminal.

With --ref, show that one row in full: an MCP entry's whole configuration (secret values withheld) or an unmanaged skill's metadata.

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--agent` <span class="cli-chip">option</span> | text |  | Only what this agent holds |
| `--ref` <span class="cli-chip">option</span> | text |  | Show one row in full: a type, a folder path or &lt;agent&gt;:&lt;entry&gt; |
| `--source` <span class="cli-chip">option</span> | text |  | With --ref on an mcp row: the config-file key |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
