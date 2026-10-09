---
title: Glossary
description: Definitions of the terms Coffer uses, from reach and kind to sync round and tidy, each linked to the page that explains it.
outline: 2
pageClass: glossary
---

# Glossary

The terms Coffer uses in its UI, CLI, API and documentation, in alphabetical order. Each
entry links to the page that explains the concept in depth.

<AzBar />

## A

### Actor

Who performed an action, as recorded in the [audit log](#audit-log): `cli`, `ui`, `api`,
`system`, or an agent's name for a write made through an MCP tool. HTTP clients set it with
the `X-Coffer-Actor` header. See the [security model](/architecture/security).

### Adopt

Take something an agent already has on disk under Coffer's management: an MCP server
entry in the agent's own config, or a skill folder placed in its skills directory by hand
(an [unmanaged skill](#unmanaged-skill)). See [Agents](/guides/agents).

### Agent

A coding agent installed on this machine and registered with Coffer, such as Claude Code
(`claude_code`) or Codex (`codex`). An agent is a [resource](#resource) of kind `agent`.
There is at most one per type on a machine, and its name is its type (`claude-code`,
`codex`); its one setting besides the model binding is its config directory. See
[Agents](/guides/agents).

### Approval

A change that would widen where a secret goes, held until a person answers it in the desktop
app: a secret cited from a new [destination](#destination) or sent to a new
[target](#target), or switching the protection off. Approving takes a [presence grant](#presence-grant); rejecting does not, and
works from any surface. A command whose change waits prints
"waiting for approval in the Coffer app" and exits `9`. See
[Secrets](/guides/secrets#approvals).

### Audit log

The append-only record of every change to Coffer's state: resource lifecycle events,
secrets revealed or resolved, approvals, config writes, provider switches, pairings. Each entry names the
[actor](#actor). See [Activity and audit](/guides/activity) and
[Observability](/architecture/observability#the-audit-log).

## B

### Binding

The link between a [skill](#skill) and an agent it is delivered to. Coffer delivers a skill
by placing a symlink to its folder in the [master store](#master-store) into the agent's
skills directory, and the **Skills** page reports any drift. See [Skills](/guides/skills).

### Built-in login

An agent's own authentication, as it was before Coffer [projected](#projection) a
[connection](#connection) into it. **Change model** on the agent's page returns an agent to
it. See [Model providers](/guides/providers).

### Built-in tool

An MCP tool Coffer itself provides, listed with the reserved `coffer__` prefix alongside
upstream tools. There are three: `coffer__search_tools`, always listed, and `coffer__ask` and
`coffer__channel_read_thread`, listed only inside a turn Coffer runs. See
[MCP tools](/reference/mcp-tools).

## C

### Channel

A messaging-app bot (Telegram or SeaTalk) through which you chat with your agents and
receive notifications when you are away from the machine. A channel is a
[resource](#resource) of kind `channel`, used by its paired owner only
([owner pairing](#owner-pairing)) and held on one machine only, like an [agent](#agent). See
[Channels](/guides/channels).

### Collection

One knowledge tree under `~/.coffer/vault/knowledge/<collection>/`: a small wiki of
[pages](#page) under `pages/`, compiled by you and your agents from the [sources](#source) kept
under `sources/`, with a `README.md` at its root. A collection is a
[resource](#resource) of kind `knowledge`. See [Knowledge](/guides/knowledge).

### `coffer-guide`

The skill Coffer ships and maintains itself. It is Coffer's manual for agents, followed by
the path, title and description of every document in every
[collection](#collection). Coffer regenerates it from the running build and refuses to
delete it. See [Skills](/guides/skills).

### `coffer run`

The command that hands [standalone secrets](#standalone-secret) to one child process:
`coffer run --secret ENV=<id> -- cmd`. The values are set only in that child's environment and
masked as `***` in its output, and each resolve is audited as `secret_resolved`. It resolves only a
secret a person allowed local programs to use, in the desktop app. It keeps a secret out of
files and transcripts by accident; it does not hide it from whoever runs the command, which is
the child's parent, so the allowance is what guards it. See [Secrets](/guides/secrets#run-a-command-with-a-secret).

### Connection

A model-provider profile: a wire protocol, a base URL and one secret. Switching a
connection on for an agent [projects](#projection) it into that agent's config. A connection
is a [resource](#resource) of kind `provider`. See [Model providers](/guides/providers).

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

### Deletion breaker

The [vault sync](#vault-sync) safeguard that holds a [sync round](#sync-round) that would
lose 20 or more files, or 5 or more that are over half of an area, in either direction, until you answer
it on the **Sync** page: **Delete N files** or **Keep the files**. Moves and renames are not losses. See
[Vault sync](/architecture/vault-sync#the-deletion-breaker).

### Delivery

Getting something Coffer holds into an agent: a [skill](#skill) by [binding](#binding). Memory
is not delivered into a session: [memory sync](#memory-sync) writes it into the agent's own
[native memory](#native-memory), which the agent loads itself. See [Skills](/guides/skills).

### Destination

A place Coffer sends a secret's plaintext: an MCP server's environment variable or HTTP
header, a channel's secret, the sync remote's push token. Each destination has a
[target](#target), the thing that actually receives the value. A secret reaches a new
destination, or a destination's new target, only after an [approval](#approval). See
[Security model](/architecture/security#a-secret-goes-somewhere-new-only-with-your-approval).

### Detect-or-spawn

How every Coffer client finds the daemon: read `daemon.json`, probe the port, and start a
daemon if none answers, under a lock so two clients never start two daemons. See
[Daemon and processes](/architecture/daemon#detect-or-spawn).

## E

### Experimental feature

A capability that ships switched off and can be switched on per machine. Two are: `knowledge`
(Knowledge) and `memory` (Memory). Vault sync and model providers graduated and are always on. While a feature is off its routes answer `404 FEATURE_DISABLED` and its UI looks absent; its data is kept. See [Experimental features](/guides/experimental-features) and
[Configuration](/reference/configuration#experimental-features).

## H

### Hub

The folder `memory/` in the [vault](#vault) that holds every memory your agents wrote for
themselves, on any of your machines: one Markdown file per memory, under `global/` or one
project (named by its repository's remote). [Vault sync](#vault-sync) carries it between
machines; only the machine a memory came from changes its file. See [Memory](/guides/memory#the-hub).

## I

### Inbox

A collection's hidden `.inbox/` directory, a drop zone: a file an agent or another machine
leaves there is adopted and kept as a [source](#source) by the next [sweep](#upkeep-pass). See
[Knowledge](/architecture/knowledge).

### Invocation log

The record of every MCP call through the gateway, upstream and built-in: server, tool,
duration, status (`ok`, `error`, `timeout` or `denied`) and session. Each call also keeps its
arguments and result, masked and cut at 16 KB, unless **Record tool call content** is switched
off ([Configuration](/reference/configuration#daemon-config-json)). See [Observability](/architecture/observability#the-mcp-invocation-log).

## J

### Join

How a machine starts syncing with a remote it has never synced with, always previewed and
never automatic: against an empty remote it pushes its vault; as a new machine it takes the
union, deleting nothing and leaving files that differ for you to choose; as a returning
machine it resumes from the commit its descriptor names. Run from the **Sync** page. See
[Vault sync](/architecture/vault-sync#joining).

## K

### Kind

The type of a [resource](#resource). Coffer registers six: `mcp_server`, `agent`,
`skill`, `channel`, `knowledge` and `provider`. The framework gives every kind the
same identity, lifecycle, audit and [reach](#reach); each kind decides what its resources do.
See [Resource framework](/architecture/resource-framework#the-six-kinds).

## M

### Machine id

A stable identifier for one machine, derived from the host and hashed before it leaves the
machine. [Vault sync](#vault-sync) uses it to tell machines apart. See [Vault sync](/guides/vault-sync).

### Master key

The key that decrypts every stored secret. It is one item in the macOS Keychain that only
Coffer's signed binaries can read, and the daemon keeps it in memory while it runs. It never syncs. Back it up
in the desktop app, which writes a key file behind a presence check, and install it on another
machine from **Settings › Security › Import a master key**. See [Secret store](/guides/secret-store#where-the-master-key-lives).

### Master store

`~/.coffer/vault/skills/`, where Coffer keeps the one authoritative copy of every managed
[skill](#skill). Agents receive symlinks into it. See [Skills](/guides/skills).

### Material

New knowledge submitted to a collection: an upload, or a file left in the
[inbox](#inbox). It becomes a [source](#source) as it stands. See
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

### Memory sync

The [upkeep pass](#upkeep-pass) that reads every registered agent's
[native memory](#native-memory), publishes what each agent wrote on this machine to the
[hub](#hub), and writes every other agent's and machine's memories into each agent's own
memory, as files the agent loads and curates itself. Coffer touches only its own copies. On by
default, hourly, and on demand with **Sync now**; the first or a large sync waits as a preview.
See [Memory](/guides/memory).

## N

### Native memory

The memory an agent keeps in its own files, such as Claude Code's per-project memory
directory. [Memory sync](#memory-sync) reads it, publishes what the agent wrote to the
[hub](#hub), and writes copies of other agents' memories beside it. The agent's page shows it
read-only. See [Memory](/guides/memory).

## O

### Owner pairing

Binding a [channel](#channel) to the one person allowed to use it. The channel's page
issues an eight-character, single-use code valid for an hour; the sender who messages the bot
with it becomes the channel's owner, and every other sender is ignored silently. See
[Channels](/guides/channels).

## P

### Page

A Markdown file under a [collection's](#collection) `pages/`: the wiki itself, written and kept
current by you and your agents from the collection's [sources](#source). See
[Knowledge](/guides/knowledge).

### Pre-apply snapshot

A git tag (`refs/tags/coffer/pre-apply/<time>`, the ten newest kept) Coffer places before a
[sync round](#sync-round) checks anything out, so the round can be rolled back from the
round's drawer. See [Vault sync](/architecture/vault-sync#rollback).

### Presence grant

The proof that a person was at the Mac. The desktop app runs Touch ID or the login password
for one operation — reveal a secret, write a key backup, approve an approval — then signs a
one-time challenge from the daemon, bound to that operation and its target, with a key
derived from the master key. The daemon acts only on a grant that verifies; a grant is used
once and expires within two minutes. See
[Security model](/architecture/security#plaintext-reaches-only-a-present-human).

### Projection

Writing a [connection's](#connection) endpoint and key reference into an agent's own config
so the agent talks to that provider. Switching back to the [built-in login](#built-in-login)
removes it. See [Model providers](/guides/providers).

## R

### Reach

Where a resource applies on this machine: its `enabled` flag together with its
[scope](#scope). Knowledge collections have no reach: each is
served to every agent. Reach is machine-local and never syncs, so each machine decides for itself
which agents see a synced resource. See
[Resource framework](/architecture/resource-framework#reach).

### Resource

Anything you manage in Coffer: an MCP server, agent, skill, channel, knowledge collection
or provider connection. Every resource has a [kind](#kind), an immutable
[uid](#uid), a name unique within its kind, and a [reach](#reach). See
[Core concepts](/start/concepts).

### Retention

Per-table limits on how long Coffer keeps log-like rows, such as the audit log and the
[invocation log](#invocation-log), enforced by a background pruner. Manage it in
**Settings → Data**. See [Observability](/architecture/observability#retention).

## S

### Scope

A resource's optional list of the agents it applies to; no list means every agent. Together
with `enabled` it forms the resource's [reach](#reach). For a [channel](#channel) the scope is
read the other way round: it names the agents the channel may drive. Set with
the kind's scope control. See [Resource framework](/architecture/resource-framework#reach).

### Secret boundary

The line Coffer holds against a prompt-injected agent running as you: a secret's plaintext
reaches only a person present at the desktop app, and a secret goes to a new
[destination](#destination) only after that person's [approval](#approval). Agents may still
read and change Coffer's configuration. See [Security model](/architecture/security).

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

### Source

A Markdown file under a [collection's](#collection) `sources/`: [material](#material) kept as
it arrived, which agents read and never edit. [Pages](#page) say which sources they draw on. See
[Knowledge](/guides/knowledge).

### Standalone secret

A secret that belongs to no resource, stored as `secret/<id>` and cited from skills and env
files as `coffer://secret/<id>`. Coffer mints the id when you run `coffer secret set --name
"Orders DB"`; a person never picks an id, only a name (the label, up to 64 characters) and a
description (up to 200), both changeable at any time. Commands use it through
[`coffer run`](#coffer-run). See
[Secrets](/guides/secrets).

### Storage class

One of the five kinds of state Coffer keeps, each in its own place under `~/.coffer`:
`vault/` (your configuration and content, in git), `local/` (true of this machine only),
`content/` (media and the chat workspace), `runs.db` (history) and `derived/` (rebuilt from
the rest). The class decides whether something syncs and whether it is safe to delete. See
[Persistence](/architecture/persistence).

### Sync round

One pass of [vault sync](#vault-sync): fetch the remote, merge it with this vault outside the
working tree, stop on any conflict, run the [deletion breaker](#deletion-breaker), take a
[pre-apply snapshot](#pre-apply-snapshot), check the merge out and push. A round that stops
waits for an answer per file on the **Sync** page. See
[Vault sync](/architecture/vault-sync#the-round).

## T

### Target

What receives a secret at a [destination](#destination), written so a person can read it in
an [approval](#approval): a stdio server's full command line with its working directory and
other environment, an HTTP server's URL, a git remote's URL, a channel's bot or app. Changing
the target asks again. See [Secrets](/guides/secrets#approvals).

### Tidy

The button on a knowledge [collection](#collection) (and
**Tidy all** on the list page) that starts your default hand-off agent in your preferred terminal,
with a prompt to merge, split and correct what is there, following the `coffer-guide`
skill, sent as the session's first message. When no managed agent is available, it offers the prompt to copy. Coffer does the
tidying through your agent, never on its own. Memory has no Tidy: each agent curates its own. See [Knowledge](/guides/knowledge).

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
reused, and the same on every synced machine. Most names can change; the uid cannot. See
[Resource framework](/architecture/resource-framework#identity).

### Unmanaged skill

A skill folder an agent has in its own skills directory that Coffer did not put there. The
agent's page lists them so you can [adopt](#adopt) or discard them. See [Skills](/guides/skills).

### Upkeep pass

Mechanical work Coffer does on a timer, without being asked: the [memory sync](#memory-sync),
and the sweep for knowledge (re-render the guide, adopt files left in the
[inbox](#inbox), file loose documents into `pages/`, commit edits made on disk). None of them calls a model. The memory sync can be switched
off or retimed from the **▾** on **Sync now** on the Memory page.
See [Memory](/architecture/memory#the-sync-pass) and [Knowledge](/architecture/knowledge#the-sweep).

## V

### Vault

The git repository at `~/.coffer/vault/` that holds your configuration and authored
content: resource files, state documents, knowledge collections, skill folders, the memory [hub](#hub), secret ciphertext and machine descriptors. It is a repository from the first use,
and every accepted change is a commit naming its [writer](#writer). More loosely, everything
Coffer keeps under `~/.coffer/`, in its five [storage classes](#storage-class). See
[Editing the vault by hand](/guides/vault-files) and [Files and directories](/reference/filesystem).

### Vault sync

Keeping the vaults on several machines the same by pulling and pushing the vault
repository to one git remote you own, in repeated [sync rounds](#sync-round). See
[Vault sync](/guides/vault-sync).

## W

### Wire

The API protocol a [connection](#connection) speaks: `anthropic`, `openai` or
`unknown`. The wire decides which agents a connection can serve. See
[Model providers](/guides/providers).

### Writer

Who made a commit in the [vault](#vault), named in its `Coffer-Writer` trailer: `user` (you,
through a Coffer surface), `disk` (a file edited in an editor, a shell or an agent's own file
tools), `agent`, `daemon`, `curation` (older history only) or `sync`. `git log`
in the vault shows it. See [Editing the vault by hand](/guides/vault-files).
