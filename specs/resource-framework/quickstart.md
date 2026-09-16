# Quickstart — Resource Framework

Everything Coffer manages is a *resource*: an MCP server, an agent, a skill, a
channel, a knowledge collection, a memory partition, a provider connection.
They are created through their own kind's command, because each kind knows what
a valid one looks like — but from the moment one exists, it is listed, read,
switched on and off, aimed at particular agents, deleted and audited through the
one surface this document covers.

## Prerequisites

- A running daemon (`coffer daemon start`) — spec daemon's quickstart covers
  getting there.
- At least one resource. If you have none yet, spec mcp-gateway's quickstart
  registers an MCP server in two commands; everything below then applies to it.

## Everything Coffer holds, in one list

```bash
coffer resource list                 # every kind
coffer resource list --kind agent    # one kind
coffer resource list --json          # for scripts
```

Each row is a `<kind>:<name>` reference, which is the only identifier any of
these commands takes:

```bash
coffer resource show mcp_server:filesystem
coffer resource show mcp_server:filesystem --json
```

## Switch one off without deleting it

```bash
coffer resource disable mcp_server:filesystem
coffer resource enable  mcp_server:filesystem
```

Disabled means "registered, configured, and not in play". A kind whose
`enabled` flag has an on-disk consequence — a skill, say — reacts to the flip
as part of the same operation, so what is on disk never disagrees with what the
list says.

## Say which agents a resource reaches

Reach is one allow-list of agent names. No list at all means every agent; an
empty list means none, which is a deliberate way to park something.

```bash
coffer scope show mcp_server:filesystem
coffer scope set  mcp_server:filesystem --agents claude-code,codex
coffer scope set  mcp_server:filesystem --no-agents     # dormant
coffer scope clear mcp_server:filesystem                # back to every agent
```

Two things worth knowing:

- **Reach is this machine's own.** It is set here, it applies here, and a sync
  round neither carries it away nor writes over it (spec vault-sync).
- **Each kind enforces it at its own door.** An out-of-reach MCP server is
  absent from that agent's tool list; an out-of-reach skill is not delivered to
  it. Setting the value is one command; what the value *does* is described by
  the kind's own spec.

A kind that takes no reach at all — `agent`, because it *is* the agent — says so
in `coffer scope show`, and refuses a non-null write.

## Delete one, and know what goes with it

```bash
coffer resource delete mcp_server:filesystem            # asks first
coffer resource delete mcp_server:filesystem --force
```

What happens, in order: the kind's own cleanup runs while the resource can
still be resolved (a failure there stops the deletion rather than leaving half
of it gone), the row goes, rows the kind owns go with it, and any credential
that no remaining resource references is released. What does **not** go is the
history: the audit log and the invocation log outlive what they describe.

## See what happened

```bash
coffer audit list
coffer audit list --kind mcp_server --name filesystem
coffer audit list --event-type resource_scope_updated --limit 200
coffer audit list --json
```

Every lifecycle change lands here, whichever surface made it, with the actor
that made it — `cli`, `api`, `ui` or `system`. The web UI shows the same rows
on its Activity page.

## Keep the logs from growing forever

```bash
coffer retention list
coffer retention set mcp_invocations --days 7
coffer retention set audit_log --forever
coffer retention prune-now                 # every table
coffer retention prune-now --table mcp_invocations
```

Defaults are seeded when the daemon first starts — the audit log at 365 days,
the MCP invocation log at 30 — and a background pass prunes on its own, so
`prune-now` is for when you do not want to wait. Only a table some spec
registered as prunable can be listed or pruned; changing a policy is itself
audited.

## Ask what the daemon is busy with

Some passes take minutes and rewrite files with a model in the loop — memory's
`organise` over a partition, knowledge's `tidy` over a collection. Whether one
is running is a fact about the daemon rather than about the button you pressed:

```bash
curl -s -H "X-Coffer-Token: $(python3 -c 'import json;print(json.load(open("'"$HOME"'/.coffer/daemon.json"))["token"])')" \
  http://127.0.0.1:8000/api/v1/upkeep/runs
```

An empty list means nothing is running — including right after a daemon
restart, which ends any pass that was in flight. Starting a pass is the kind's
own command; how often one runs on a timer is spec internal-engine's.

## Why there is no `coffer resource create`

Creation is the one thing this surface does not generalise. A skill needs its
master folder, an agent needs to be found on disk, a channel needs its binding
checked — invariants the framework cannot know and must not guess. So each kind
registers through its own command (`coffer mcp add`, `coffer skill add`,
`coffer agent add`, …), and the kind-agnostic create route accepts only kinds
that have declared they need nothing more than a valid config.

Everything after that moment is on this page.

## Troubleshooting

| Symptom                                                      | Most likely cause                                        | Fix                                                                                     |
| ------------------------------------------------------------ | -------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `unknown kind` on any command                                | The kind's name is misspelled, or its spec is not wired  | `coffer resource list` names every kind that exists.                                     |
| A scope write returns a validation error                     | The kind takes no reach, or the payload named an unknown field | `coffer scope show <ref>` reports `supports_scope`; an unknown field is refused rather than dropped. |
| A resource reappears after deletion                          | It was re-imported by a sync round                       | Delete it on the machine that still has it, or narrow what converges (spec vault-sync).  |
| `coffer retention set` says the table is unknown             | Nothing registered that table as prunable                | `coffer retention list` is the whole set.                                                |
| The audit log is empty on a fresh vault                      | Nothing has happened yet                                 | Make any change; the first entry appears immediately.                                    |
