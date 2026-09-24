---
title: Glossary
description: Definitions of the terms Coffer uses, from reach and kind to converge round and curation pass, each linked to the page that explains it.
outline: 2
---

# Glossary

The terms Coffer uses in its UI, CLI, API and documentation, in alphabetical order. Each
entry links to the page that explains the concept in depth.

## A

### Actor

Who performed an action, as recorded in the [audit log](#audit-log): `cli`, `ui`, `api`,
`system`, or an agent's name for a write made through an MCP tool. HTTP clients set it with
the `X-Coffer-Actor` header. See [REST API](/reference/rest-api#authentication).

### Adopt

Take something an agent already has on disk under Coffer's management: an MCP server
entry in the agent's own config, or a skill folder placed in its skills directory by hand
(an [unmanaged skill](#unmanaged-skill)). See [Agents](/guides/agents).

### Agent

A coding agent installed on this machine and registered with Coffer, such as Claude Code
(`claude_code`) or Codex (`codex`). An agent is a [resource](#resource) of kind `agent`,
identified by its config directory. See [Agents](/guides/agents).

### Aggregate pass

The [upkeep pass](#upkeep-pass) that reads every enabled agent's
[native memory](#native-memory) into Coffer's memory as [raw entries](#raw-entry). Coffer
never writes back into an agent's own memory. See [Memory](/architecture/memory#the-aggregation-pass).

### Audit log

The append-only record of every change to Coffer's state: resource lifecycle events,
credential reads, config writes, provider switches, pairings. Each entry names the
[actor](#actor). See [Activity and audit](/guides/activity) and
[Observability](/architecture/observability#the-audit-log).

## B

### Binding

The link between a [skill](#skill) and an agent it is delivered to. Coffer delivers a skill
by placing a symlink to its folder in the [master store](#master-store) into the agent's
skills directory, and `coffer skill verify` reports any drift. See [Skills](/guides/skills).

### Build channel

Whether a build is `stable` (a tagged release) or `dev` (everything else, including source
runs). The channel decides the default state of every
[experimental feature](#experimental-feature). See
[Distribution and releases](/architecture/distribution#release-channels).

### Built-in login

An agent's own authentication, as it was before Coffer [projected](#projection) a
[connection](#connection) into it. `coffer provider use-builtin <wire>` returns an agent to
it. See [Model providers](/guides/providers).

### Built-in tool

An MCP tool Coffer itself provides, listed with the reserved `coffer__` prefix alongside
upstream tools: `coffer__write`, `coffer__recall`, `coffer__diagnose` and
`coffer__search_tools`. See [MCP tools](/reference/mcp-tools).

## C

### Channel

A messaging-app bot (Telegram or SeaTalk) through which you chat with your agents and
receive notifications when you are away from the machine. A channel is a
[resource](#resource) of kind `channel`, used by its paired owner only
([owner pairing](#owner-pairing)) and run by one machine ([`runs_on`](#runs-on)). See
[Channels](/guides/channels).

### Collection

One knowledge tree: a directory of Markdown documents under
`~/.coffer/knowledge/<collection>/`, written together by you and Coffer. A collection is a
[resource](#resource) of kind `knowledge`. See [Knowledge](/guides/knowledge).

### `coffer-guide`

The skill Coffer ships and maintains itself. It is Coffer's manual for agents, followed by
the path, title and description of every document in the enabled
[collections](#collection). Coffer regenerates it from the running build and refuses to
delete it. See [Skills](/guides/skills).

### Connection

A model-provider profile: a wire protocol, a base URL and one credential. Switching a
connection on for an agent [projects](#projection) it into that agent's config. A connection
is a [resource](#resource) of kind `provider`. See [Model providers](/guides/providers).

### Converge round

One pass of [vault sync](#vault-sync): Coffer exports the vault into a git working tree and
commits it, merges the remote branch, applies the merged diff back into the vault, pushes, and
advances the [pointer](#pointer). See [Vault sync](/architecture/vault-sync#the-converge-round).

### Curation owner

The one machine allowed to run the [curation pass](#curation-pass) automatically, so two
synced machines never rewrite the same collection at once. Set with
`coffer engine curate-owner`. See [Knowledge](/architecture/knowledge#the-owner-machine).

### Curation pass

A bounded rewrite of one [collection](#collection) by the [internal engine](#internal-engine):
it takes one pending item (new [material](#material) from the [inbox](#inbox), or a document
edited since it was last curated), merges it into the collection's documents, and writes at
most eight files. It runs on a timer and on demand (`coffer knowledge curate`). See
[Knowledge](/architecture/knowledge#the-curation-pass).

## D

### Daemon

The long-running Coffer process on `127.0.0.1`. It owns all state, serves the management
API, the web UI and the MCP endpoint, and runs the upkeep workers. The CLI and the
[shim](#shim) start it when it is not running. See [Running the daemon](/guides/daemon) and
[Daemon and processes](/architecture/daemon).

### `daemon.json`

The runtime discovery file, `~/.coffer/daemon.json`: the running daemon's port, process id
and API token, mode `0600`, written at start and removed at exit. Its companion
`daemon-config.json` holds settings read before the daemon binds: the fixed port, the machine
name and the experimental-feature switches. See [Files and directories](/reference/filesystem#daemon-files).

### Deletion guard

The [vault sync](#vault-sync) safeguard that holds a [converge round](#converge-round)
whose diff would lose 20 or more documents, or more than 20% of an area, in either
direction, until you confirm or reject it with `coffer sync confirm` or `coffer sync reject`.
See [Vault sync](/architecture/vault-sync#the-deletion-guard).

### Delivery

Getting something Coffer holds into an agent: a [skill](#skill) by [binding](#binding), and
[memory](#partition) by a session-start hook Coffer installs in the agent's settings. See
[Memory](/guides/memory).

### Detect-or-spawn

How every Coffer client finds the daemon: read `daemon.json`, probe the port, and start a
daemon if none answers, under a lock so two clients never start two daemons. See
[Daemon and processes](/architecture/daemon#detect-or-spawn).

### Distil pass

The [upkeep pass](#upkeep-pass) that turns a [partition's](#partition) [raw entries](#raw-entry)
into [notes](#note) and rewrites its index, `MEMORY.md`. See [Memory](/architecture/memory#the-distil-pass).

## E

### Experimental feature

A capability that ships switched off on stable builds and can be switched on per machine:
`vault_sync`, `knowledge` and `memory`. While a feature is off its routes answer
`404 FEATURE_DISABLED`, its tools leave the MCP tool list, and its UI is hidden; its data is
kept. See [Experimental features](/guides/experimental-features) and
[Configuration](/reference/configuration#experimental-features).

## I

### Inbox

A collection's hidden `.inbox/` directory, where new [material](#material) waits for the
[curation pass](#curation-pass). It is the one hidden directory Coffer writes inside a
collection. See [Knowledge](/architecture/knowledge).

### Internal engine

Coffer's own use of a language model, for its [upkeep passes](#upkeep-pass): curating
knowledge and distilling memory. It runs on the [connection](#connection) you mark as the
internal-engine default. Without one, curation files new knowledge as it stands and the
distil pass turns each raw entry into a note of its own. See [Model providers](/guides/providers).

### Invocation log

The record of every MCP call through the gateway, upstream and built-in: server, tool,
duration, status (`ok`, `error`, `timeout` or `denied`) and session. It never holds arguments or
results. See [Observability](/architecture/observability#the-mcp-invocation-log).

## K

### Kind

The type of a [resource](#resource). Coffer registers seven: `mcp_server`, `agent`,
`skill`, `channel`, `knowledge`, `memory` and `provider`. The framework gives every kind the
same identity, lifecycle, audit and [reach](#reach); each kind decides what its resources do.
See [Resource framework](/architecture/resource-framework#the-seven-kinds).

## M

### Machine id

A stable identifier for one machine, derived from the host and hashed before it leaves the
machine. [Vault sync](#vault-sync) uses it to tell machines apart, and a channel's
[`runs_on`](#runs-on) names one. See [Vault sync](/guides/vault-sync).

### Master key

The key that decrypts every stored credential. It lives in `master.key` beside the database
(mode `0600`) by default, or in the OS keychain if you move it there. It never syncs; move it
between machines with `coffer sync key export` and `coffer sync key import`. See
[Credentials](/guides/credentials).

### Master store

`~/.coffer/skills/`, where Coffer keeps the one authoritative copy of every managed
[skill](#skill). Agents receive symlinks into it. See [Skills](/guides/skills).

### Material

New knowledge submitted to a collection, from `coffer__write`, `coffer knowledge write`,
an upload or a channel. Material waits in the [inbox](#inbox) until the
[curation pass](#curation-pass) merges it into the documents. See
[Knowledge](/guides/knowledge).

### MCP gateway

The part of the daemon that serves `/mcp`: it aggregates the tools, resources and prompts of
every enabled [MCP server](#mcp-server) in the session's [reach](#reach), adds the
[built-in tools](#built-in-tool), and routes each call. See
[MCP gateway](/architecture/mcp-gateway#lifecycle-of-a-tools-call).

### MCP server

An upstream Model Context Protocol server you register with Coffer, over stdio or HTTP. It
is a [resource](#resource) of kind `mcp_server`, and its tools reach agents as
`<server>__<tool>`. See [MCP servers](/guides/mcp-servers).

## N

### Native memory

The memory an agent keeps in its own files, such as Claude Code's per-project memory
directory. Coffer reads it during the [aggregate pass](#aggregate-pass) and shows it read-only
on the agent's page. See [Memory](/guides/memory).

### Note

One topic in Coffer's memory, written by the [distil pass](#distil-pass) as a Markdown file
in a [partition's](#partition) `notes/` directory. `coffer__recall` returns notes' paths. See
[Memory](/guides/memory).

## O

### Owner pairing

Binding a [channel](#channel) to the one person allowed to use it. `coffer channel pair`
issues an eight-character, single-use code valid for an hour; the sender who messages the bot
with it becomes the channel's owner, and every other sender is ignored silently. See
[Channels](/guides/channels).

## P

### Partition

One unit of Coffer's memory: `global`, or one repository. Each partition is a directory
under `~/.coffer/memory/` holding its [notes](#note), its `MEMORY.md` index and its
[raw entries](#raw-entry). A partition is a [resource](#resource) of kind `memory`. See
[Memory](/guides/memory).

### Pointer

The machine-local record of the last commit this vault provably absorbed from the sync
remote. Every [converge round](#converge-round) diffs against it; a machine with no pointer
is joining. See [Vault sync](/architecture/vault-sync#the-pointer-the-retry-set-and-the-not-applicable-set).

### Pre-apply snapshot

A git tag Coffer places before applying a [converge round](#converge-round), so the round
can be rolled back with `coffer sync rollback`. See [Vault sync](/architecture/vault-sync#recovery).

### Projection

Writing a [connection's](#connection) endpoint and key reference into an agent's own config
so the agent talks to that provider. Switching back to the [built-in login](#built-in-login)
removes it. See [Model providers](/guides/providers).

## R

### Raw entry

One fact read out of an agent's [native memory](#native-memory) by the
[aggregate pass](#aggregate-pass), kept in the partition's hidden `.raw/` directory until the
[distil pass](#distil-pass) turns it into [notes](#note). See [Memory](/architecture/memory#stable-raw-entries).

### Reach

Where a resource applies on this machine: its `enabled` flag together with its
[scope](#scope). Reach is machine-local and never syncs, so each machine decides for itself
which agents see a synced resource. See
[Resource framework](/architecture/resource-framework#reach).

### Resource

Anything you manage in Coffer: an MCP server, agent, skill, channel, knowledge collection,
memory partition or provider connection. Every resource has a [kind](#kind), an immutable
[uid](#uid), a name unique within its kind, and a [reach](#reach). See
[Core concepts](/start/concepts).

### Retention

Per-table limits on how long Coffer keeps log-like rows, such as the audit log and the
[invocation log](#invocation-log), enforced by a background pruner. Manage it with
`coffer retention`. See [Observability](/architecture/observability#retention).

### Retry set

The paths a [converge round](#converge-round) could not apply. Coffer retries them on the
next round and never exports them as deletions meanwhile. See
[Vault sync](/architecture/vault-sync#the-pointer-the-retry-set-and-the-not-applicable-set).

### `runs_on`

The [machine id](#machine-id) of the one machine whose daemon runs a [channel's](#channel)
adapter. The channel's settings sync to every machine; only that machine connects to the
messaging platform. Set with `coffer channel bind`. See [Channels](/guides/channels).

## S

### Scope

A resource's optional list of the agents it applies to; no list means every agent. Together
with `enabled` it forms the resource's [reach](#reach). For a [channel](#channel) the scope is
read the other way round: it names the agents the channel may drive. Set with
`coffer scope set`. See [Resource framework](/architecture/resource-framework#reach).

### Session

One MCP client connection to the gateway. Each session gets its own upstream server
processes and its own agent identity, reported by the [shim](#shim) at the handshake. Idle
sessions are reaped. See [MCP gateway](/architecture/mcp-gateway#sessions-and-identity).

### Shim

`coffer-mcp-shim`, the small stdio program an agent launches as its `coffer` MCP server. It
forwards the agent's MCP messages to the daemon's `/mcp` endpoint, starts the daemon if
needed, and reports the agent's uid (`--agent-uid`). See
[Connect a client](/guides/connect-a-client).

### Skill

A folder with a `SKILL.md` that teaches an agent a task. Coffer keeps managed skills in its
[master store](#master-store) and [binds](#binding) each to the agents in its reach. A skill
is a [resource](#resource) of kind `skill`. See [Skills](/guides/skills).

## T

### Tiering

The gateway's listing budget: when upstream tools outnumber it, `tools/list` carries the
most-used tools (at least one per server) and every other tool stays callable by name and
findable with `coffer__search_tools`. See [MCP tools](/reference/mcp-tools#tiering).

### Trace id

A per-request identifier the daemon returns in the `X-Coffer-Trace` header and stamps on
every log line the request produces, so a failed response can be matched to its log records.
See [Observability](/architecture/observability#trace-ids).

### Turn

One exchange in a chat conversation: your message and the agent's streamed reply, including
its tool calls. A conversation runs one turn at a time and queues further messages. See
[Chat and turns](/architecture/chat#the-turn-orchestrator).

## U

### uid

A resource's permanent identifier: a random 32-character hex string minted once, never
reused, and the same on every synced machine. Names can change; the uid cannot. See
[Resource framework](/architecture/resource-framework#identity).

### Unmanaged skill

A skill folder an agent has in its own skills directory that Coffer did not put there. The
agent's page lists them so you can [adopt](#adopt) or remove them. See [Skills](/guides/skills).

### Upkeep pass

Work Coffer does on a timer, without being asked: `aggregate` and `distil` for memory,
`curate` for knowledge. Each can be switched off or retimed with `coffer engine upkeep set`.
See [Memory](/architecture/memory#workers-and-scheduling) and [Knowledge](/architecture/knowledge#the-sweep).

## V

### Vault

Everything Coffer holds for you on one machine, under `~/.coffer/`: the database of
resources and encrypted credentials, the skill master store, knowledge collections and
memory partitions. See [Files and directories](/reference/filesystem).

### Vault sync

Keeping vaults on several machines converged through one git remote you own, by repeated
[converge rounds](#converge-round). An [experimental feature](#experimental-feature) keyed
`vault_sync`. See [Vault sync](/guides/vault-sync).

## W

### Wire

The API protocol a [connection](#connection) speaks: `anthropic`, `openai`, `ollama` or
`unknown`. The wire decides which agents a connection can serve. See
[Model providers](/guides/providers).
