---
title: REST API reference
description: The daemon's management API — base URL, authentication, errors, tracing and every route.
---

# REST API reference

The Coffer daemon serves a JSON management API on loopback. The web UI, the desktop app and
the `coffer` CLI all use it; you can call it too, for scripting. This page covers the
conventions every route shares and lists every route the daemon mounts.

::: info Generated page
The route tables below are generated from the daemon's OpenAPI document by
`docs-site/scripts/gen_rest_reference.py`. Regenerate with `make docs-reference`;
`make lint` fails when the page and the daemon disagree.
:::

## Base URL

```text
http://127.0.0.1:8000/api/v1
```

The daemon binds `127.0.0.1` only. The port is `8000` unless you set another one with
`coffer daemon port set <port>`; the port of the running daemon is always in
`~/.coffer/daemon.json`. See [Running the daemon](/guides/daemon).

The daemon also serves its live OpenAPI document at `/api/v1/openapi.json`, and the MCP
endpoint for agents at `/mcp` (see [MCP tools](/reference/mcp-tools)).

## Authentication

Every route except `GET /api/v1/daemon/status` requires the daemon's API token in the
`X-Coffer-Token` header. The daemon generates a fresh token each time it starts and writes it,
with the port and its process id, to `~/.coffer/daemon.json` (mode `0600`):

```sh
TOKEN=$(python3 -c 'import json,os; print(json.load(open(os.path.expanduser("~/.coffer/daemon.json")))["token"])')
curl -s -H "X-Coffer-Token: $TOKEN" http://127.0.0.1:8000/api/v1/resources
```

| Header | Direction | Meaning |
| --- | --- | --- |
| `X-Coffer-Token` | request | The API token. Missing or wrong: `401 UNAUTHENTICATED`. Before the daemon is ready: `503 DAEMON_NOT_READY`. |
| `X-Coffer-Actor` | request | Optional. Who is acting, recorded in the audit log: a lowercase identifier matching `[a-z][a-z0-9_-]{0,31}` (the CLI sends `cli`, the web UI `ui`). Defaults to `api`; any other shape is `400`. |
| `X-Coffer-Trace` | both | Optional on requests; always on responses. See [Tracing](#tracing). |

`coffer daemon rotate-token` replaces the token and rewrites `daemon.json`.

::: warning Loopback only
The daemon refuses any request whose `Host` header does not name a loopback address
(`127.0.0.1`, `localhost`, `::1`) with `421 HOST_NOT_LOOPBACK`. This defends against DNS
rebinding; see the [security model](/architecture/security).
:::

## Errors

Every error response has the same envelope:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "no mcp_server named 'ghost'",
    "details": {}
  }
}
```

`code` is stable and machine-readable; `message` is for people; `details` carries structured
context such as `reason`, `hint` or `feature` when the error has one. Request-validation
failures are `422 CONFIG_INVALID` and deliberately do not echo the submitted values. The full
list of codes and their HTTP statuses is in [Error codes](/reference/error-codes).

## Tracing

The daemon gives every request a trace id and returns it in the `X-Coffer-Trace` response
header, error or not. Every daemon log line written while serving that request carries the
same id as `trace_id`, so you can find a failed request's log records with
`grep <trace-id> ~/.coffer/logs/daemon.log`. You may send your own `X-Coffer-Trace` to tie
several calls together; the daemon keeps only `A-Z a-z 0-9 . _ : -` and at most 64
characters, and generates a fresh id if nothing survives. See
[Observability](/architecture/observability).

## Experimental features

Routes that belong to an [experimental feature](/guides/experimental-features) answer
`404 FEATURE_DISABLED` (with `details.feature`) while that feature is switched off on the
machine, exactly like a route the build does not have. The tables below mark those groups.

## Routes

The daemon mounts 160 operations in 20 groups. Groups follow the order the daemon registers its routers in; paths are relative to the host root.

| Group | Operations |
| --- | --- |
| [daemon](#daemon) | 8 |
| [resources](#resources) | 9 |
| [audit](#audit) | 1 |
| [retention](#retention) | 3 |
| [upkeep](#upkeep) | 1 |
| [credentials](#credentials) | 5 |
| [settings](#settings) | 2 |
| [sync](#sync) | 19 |
| [internal-engine](#internal-engine) | 6 |
| [agents](#agents) | 29 |
| [fs](#fs) | 5 |
| [skills](#skills) | 9 |
| [mcp](#mcp) | 10 |
| [knowledge](#knowledge) | 8 |
| [memory](#memory) | 12 |
| [agent-providers](#agent-providers) | 2 |
| [models](#models) | 3 |
| [chat](#chat) | 14 |
| [channels](#channels) | 3 |
| [providers](#providers) | 11 |

### daemon

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/daemon/status` | Get Status (no token required) |
| `POST` | `/api/v1/daemon/rotate-token` | Rotate Token |
| `GET` | `/api/v1/daemon/residency` | Get Residency |
| `PUT` | `/api/v1/daemon/residency` | Install or remove the login service, and say what is true afterwards. |
| `POST` | `/api/v1/daemon/shutdown` | Shutdown Daemon |
| `GET` | `/api/v1/daemon/logs` | The tail of ``daemon.log``, newest-first — the same record ``coffer__diagnose`` reads, for the human looking at the Activity page instead of an agent. |
| `GET` | `/api/v1/daemon/features` | List Features |
| `PUT` | `/api/v1/daemon/features/{key}` | Switch one feature on this machine, at once and without a restart. |

### resources

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/resources` | List Resources |
| `POST` | `/api/v1/resources` | Register Resource |
| `GET` | `/api/v1/resources/{uid}` | Get Resource |
| `PATCH` | `/api/v1/resources/{uid}` | Edit a resource's label, description or config. |
| `DELETE` | `/api/v1/resources/{uid}` | Delete Resource |
| `POST` | `/api/v1/resources/{uid}/enable` | Enable Resource |
| `POST` | `/api/v1/resources/{uid}/disable` | Disable Resource |
| `GET` | `/api/v1/resources/{uid}/scope` | Get Resource Scope |
| `PUT` | `/api/v1/resources/{uid}/scope` | Update Resource Scope |

### audit

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/audit` | List Audit |

### retention

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/retention/policies` | List Policies |
| `PATCH` | `/api/v1/retention/policies/{table_name}` | Update Policy |
| `POST` | `/api/v1/retention/prune` | Prune Now |

### upkeep

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/upkeep/runs` | List Runs |

### credentials

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/credentials` | Every credential ref a registered resource cites, with its presence. |
| `POST` | `/api/v1/credentials` | Store `value` under `ref` in the encrypted credential store. |
| `GET` | `/api/v1/credentials/{ref}/exists` | Report whether a secret is stored under `ref`. |
| `GET` | `/api/v1/credentials/{ref}` | Return the secret value stored under `ref`. |
| `DELETE` | `/api/v1/credentials/{ref}` | Remove `ref` from the credential store. |

### settings

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/settings/credentials` | Report where the master key currently lives. |
| `PUT` | `/api/v1/settings/credentials` | Relocate the master key. |

### sync

::: tip Experimental feature `vault_sync`
Routes under this feature's prefix answer `404 FEATURE_DISABLED` while `vault_sync` is off.
:::

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/v1/sync/run` | Run Round |
| `GET` | `/api/v1/sync/join` | State the join ``/adopt`` would make, applying nothing. |
| `POST` | `/api/v1/sync/adopt` | Join the configured remote. |
| `POST` | `/api/v1/sync/confirm` | Confirm |
| `POST` | `/api/v1/sync/reject` | Reject |
| `POST` | `/api/v1/sync/rebuild` | Rebuild this machine from the remote, discarding local-only documents. |
| `POST` | `/api/v1/sync/rollback` | Rollback |
| `POST` | `/api/v1/sync/restore` | Restore |
| `GET` | `/api/v1/sync/remote` | Get Remote |
| `PUT` | `/api/v1/sync/remote` | Put Remote |
| `DELETE` | `/api/v1/sync/remote` | Delete Remote |
| `GET` | `/api/v1/sync/status` | Status |
| `GET` | `/api/v1/sync/runs` | Every round this vault has run, newest first. |
| `GET` | `/api/v1/sync/machines` | List Machines |
| `PATCH` | `/api/v1/sync/machines/self` | Rename this machine. |
| `DELETE` | `/api/v1/sync/machines/{machine_id}` | Retire Machine |
| `GET` | `/api/v1/sync/key/fingerprint` | Key Fingerprint |
| `POST` | `/api/v1/sync/key/export` | Export Key |
| `POST` | `/api/v1/sync/key/import` | Import Key |

### internal-engine

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/internal-engine-config` | Get Config |
| `PUT` | `/api/v1/internal-engine-config` | Update Config |
| `PUT` | `/api/v1/internal-engine-config/upkeep` | Change one pass's switch or timer. |
| `PUT` | `/api/v1/internal-engine-config/curation-owner` | Name the machine that runs the curation pass; ``null`` clears it. |
| `PUT` | `/api/v1/internal-engine-config/timeout` | Bound one call to Coffer's own model, or return it to the default. |
| `PUT` | `/api/v1/internal-engine-config/transcribe-model` | Choose the model Coffer transcribes speech with, or stop transcribing. |

### agents

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/agents` | List Agents |
| `POST` | `/api/v1/agents` | Register Agent |
| `GET` | `/api/v1/agents/candidates` | Discover installed agents that aren't registered yet (read-only). |
| `GET` | `/api/v1/agents/{uid}` | Get Agent |
| `PATCH` | `/api/v1/agents/{uid}` | Update Agent |
| `DELETE` | `/api/v1/agents/{uid}` | Delete Agent |
| `GET` | `/api/v1/agents/{uid}/config-files` | List Config Files |
| `GET` | `/api/v1/agents/{uid}/config-files/{key}/files/{relpath}` | Read Config Dir File |
| `PUT` | `/api/v1/agents/{uid}/config-files/{key}/files/{relpath}` | Write Config Dir File |
| `DELETE` | `/api/v1/agents/{uid}/config-files/{key}/files/{relpath}` | Delete Config Dir File |
| `GET` | `/api/v1/agents/{uid}/config-files/{key}` | Read Config File |
| `PUT` | `/api/v1/agents/{uid}/config-files/{key}` | Write Config File |
| `GET` | `/api/v1/agents/{uid}/mcp-install` | Mcp Install Status |
| `POST` | `/api/v1/agents/{uid}/mcp-install` | Install Mcp |
| `DELETE` | `/api/v1/agents/{uid}/mcp-install` | Uninstall Mcp |
| `GET` | `/api/v1/agents/{uid}/mcp-entries` | List Mcp Entries |
| `DELETE` | `/api/v1/agents/{uid}/mcp-entries/{entry}` | Delete Mcp Entry |
| `POST` | `/api/v1/agents/{uid}/mcp-entries/{entry}/adopt` | Adopt Mcp Entry |
| `GET` | `/api/v1/agents/{uid}/plugins` | List Plugins |
| `PATCH` | `/api/v1/agents/{uid}/plugins/{plugin_id}` | Patch Plugin |
| `DELETE` | `/api/v1/agents/{uid}/plugins/{plugin_id}` | Delete Plugin |
| `GET` | `/api/v1/agents/{uid}/native-memory` | The agent's own native memory stores, most populated first. |
| `GET` | `/api/v1/agents/{uid}/native-memory/files` | One native-memory store's directory, as a read-only tree. |
| `GET` | `/api/v1/agents/{uid}/native-memory/files/content` | Read one file inside a native-memory store, for the read-only preview. |
| `GET` | `/api/v1/agents/{uid}/transcripts` | List an agent's transcript sessions with search, filter, and sort. |
| `GET` | `/api/v1/agents/{uid}/transcripts/session` | Render one of the agent's conversations: its summary and a page of turns. |
| `GET` | `/api/v1/agents/{uid}/unmanaged-skills` | List Unmanaged Skills |
| `POST` | `/api/v1/agents/{uid}/unmanaged-skills/{skill}/adopt` | Adopt Unmanaged Skill |
| `DELETE` | `/api/v1/agents/{uid}/unmanaged-skills/{skill}` | Delete Unmanaged Skill |

### fs

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/fs/browse` | List the immediate subdirectories of `path` (defaults to the home dir). |
| `POST` | `/api/v1/fs/open` | Open `path` in the preferred editor (`with`) or the OS default app. |
| `POST` | `/api/v1/fs/reveal` | Select / reveal `path` in the OS file manager. |
| `POST` | `/api/v1/fs/pick-folder` | Open the host's native folder dialog and return the chosen directory. |
| `GET` | `/api/v1/fs/editors` | List GUI editors detected on this machine for the preferred-editor picker. |

### skills

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/skills` | List Skills |
| `POST` | `/api/v1/skills/import` | Import Skill |
| `GET` | `/api/v1/skills/{uid}` | Get Skill |
| `DELETE` | `/api/v1/skills/{uid}` | Delete Skill |
| `POST` | `/api/v1/skills/verify` | Verify Skills |
| `POST` | `/api/v1/skills/repair` | Repair Skills |
| `GET` | `/api/v1/skills/{uid}/files` | Return the skill's master folder as a read-only file tree. |
| `GET` | `/api/v1/skills/{uid}/files/content` | Read a single file's contents from the skill's master folder. |
| `PUT` | `/api/v1/skills/{uid}/files/content` | Overwrite one existing text file in the skill's master folder. |

### mcp

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/mcp` | Open the SSE stream for downstream-bound server notifications. |
| `POST` | `/mcp` | Process one JSON-RPC request from a downstream MCP client. |
| `GET` | `/api/v1/resources/mcp_server/{uid}/capabilities` | Return the live (cache-aware) capability list for one MCP server. |
| `GET` | `/api/v1/resources/mcp_server/{uid}/status` | Per-server status from persisted state — health record (from /test), discovered capabilities, or last invocation. |
| `POST` | `/api/v1/resources/mcp_server/{uid}/capabilities/{capability_type}/enable` | Enable a specific capability for the MCP server this uid names. |
| `POST` | `/api/v1/resources/mcp_server/{uid}/capabilities/{capability_type}/disable` | Disable a specific capability for the MCP server this uid names. |
| `POST` | `/api/v1/resources/mcp_server/{uid}/refresh` | Invalidate the discovery cache for this server and re-query upstream. |
| `POST` | `/api/v1/resources/mcp_server/{uid}/test` | Open a transient upstream session, run MCP initialize, return health info. |
| `GET` | `/api/v1/resources/mcp_server/{uid}/invocations` | Query invocation records for this server with optional filters. |
| `GET` | `/api/v1/mcp/invocations` | Every server's invocations on one timeline, newest-first. |

### knowledge

::: tip Experimental feature `knowledge`
Routes under this feature's prefix answer `404 FEATURE_DISABLED` while `knowledge` is off.
:::

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/knowledge/collections` | List Collections |
| `POST` | `/api/v1/knowledge/collections` | Create Collection |
| `GET` | `/api/v1/knowledge/tree` | Read Tree |
| `GET` | `/api/v1/knowledge/file` | Read File |
| `DELETE` | `/api/v1/knowledge/file` | Delete File |
| `POST` | `/api/v1/knowledge/material` | Submit Material |
| `POST` | `/api/v1/knowledge/collections/{uid}/curate` | Curate |
| `POST` | `/api/v1/knowledge/upload` | Upload |

### memory

::: tip Experimental feature `memory`
Routes under this feature's prefix answer `404 FEATURE_DISABLED` while `memory` is off.
:::

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/memory/partitions` | List Partitions |
| `POST` | `/api/v1/memory/sync` | Run aggregation over every registered, enabled agent's native memory. |
| `POST` | `/api/v1/memory/partitions/{uid}/distil` | Turn one partition's raw entries into notes, and rewrite its index. |
| `GET` | `/api/v1/memory/partitions/{uid}/notes` | Every note in one partition, read from ``notes/`` at call time. |
| `GET` | `/api/v1/memory/partitions/{uid}/notes/{slug}` | One note, whole. |
| `GET` | `/api/v1/memory/partitions/{uid}/retired` | ``RETIRED.md``, read back — newest first. |
| `GET` | `/api/v1/memory/partitions/{uid}/files` | The partition's own directory, as a read-only tree. |
| `GET` | `/api/v1/memory/partitions/{uid}/files/content` | One file out of the partition's directory. |
| `POST` | `/api/v1/memory/context` | Compose the session-start payload for one directory. |
| `GET` | `/api/v1/memory/delivery` | Delivery state for one agent, or for every agent with an adapter. |
| `POST` | `/api/v1/memory/delivery/{agent_uid}/install` | Write Coffer's hook into one agent's own settings file. |
| `DELETE` | `/api/v1/memory/delivery/{agent_uid}` | Remove Delivery |

### agent-providers

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/agent-providers` | List the registered agent providers, each with an availability flag. |
| `GET` | `/api/v1/agent-providers/{agent_key}/models` | The models a picker should offer for this agent. |

### models

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/v1/models/list-models` | List the models a provider exposes (empty + message → enter manually). |
| `POST` | `/api/v1/models/test-connection` | Probe a chat provider with a minimal request; 200 with ok=true/false. |
| `POST` | `/api/v1/models/detect-protocol` | Classify the endpoint's wire so the dialog needs no manual type selector. |

### chat

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/chat/conversations` | List conversations, newest first. |
| `POST` | `/api/v1/chat/conversations` | Create a conversation for the named Coffer-managed agent. |
| `GET` | `/api/v1/chat/conversations/{id}` | Get a single conversation by id. |
| `PATCH` | `/api/v1/chat/conversations/{id}` | Rename a conversation. |
| `DELETE` | `/api/v1/chat/conversations/{id}` | Delete a conversation and all its messages. |
| `GET` | `/api/v1/chat/conversations/{id}/agent-config` | Read a conversation's agent config (cwd, model, effort). |
| `PATCH` | `/api/v1/chat/conversations/{id}/agent-config` | Set a managed agent's own model and effort for a conversation. |
| `POST` | `/api/v1/chat/conversations/{id}/archive` | Archive a conversation — hidden from the default list, still restorable. |
| `POST` | `/api/v1/chat/conversations/{id}/unarchive` | Restore an archived conversation back into the active list. |
| `GET` | `/api/v1/chat/conversations/{id}/messages` | Return message history for a conversation, ordered by seq ascending. |
| `POST` | `/api/v1/chat/conversations/{id}/messages` | Start a turn for the message, or enqueue it behind the in-flight one. |
| `GET` | `/api/v1/chat/conversations/{id}/events` | Subscribe to the conversation's live turn events. |
| `PUT` | `/api/v1/chat/conversations/{id}/pending` | Replace the conversation's pending message queue (resume / drop / reorder). |
| `POST` | `/api/v1/chat/conversations/{id}/interrupt` | Stop the conversation's in-flight turn (keeping its partial output) and pause the pending queue. |

### channels

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/v1/channels/{uid}/pairing-code` | Issue Pairing Code |
| `GET` | `/api/v1/channels/{uid}/status` | Channel Status |
| `POST` | `/api/v1/channels/{uid}/notify` | Notify Channel |

### providers

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/v1/providers` | List all provider profiles. |
| `POST` | `/api/v1/providers` | Create a provider profile (422 when the credential source is invalid). |
| `GET` | `/api/v1/providers/active-key/{wire}` | Back-compat: the decrypted key of the connection active for ``wire``'s agent (legacy ``--wire`` helper). |
| `GET` | `/api/v1/providers/{uid}/key` | The decrypted key of a SPECIFIC connection — what Claude Code's projected ``apiKeyHelper`` (``coffer provider key --connection-uid <uid>``) fetches, so the agent always reads exactly the activated connection's key (no wire+active mismatch). |
| `GET` | `/api/v1/providers/{uid}` | Get one provider profile (404 if absent). |
| `PATCH` | `/api/v1/providers/{uid}` | Partially update a provider profile. |
| `DELETE` | `/api/v1/providers/{uid}` | Delete a provider profile (404 if absent). |
| `POST` | `/api/v1/providers/{uid}/activate` | Switch: make this profile active for its wire format and project it. |
| `POST` | `/api/v1/providers/use-builtin/{wire}` | Switch this wire's agent(s) back to their OWN built-in login: remove Coffer's projection from the native config and clear the active connection. |
| `POST` | `/api/v1/providers/{uid}/internal-default` | Make this connection Coffer's internal-engine default (≤1 globally). |
| `POST` | `/api/v1/providers/{uid}/transcribe-default` | Make this connection the one Coffer transcribes speech on (≤1 globally). |
