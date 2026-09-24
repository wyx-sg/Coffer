---
title: Decision records
description: An index of Coffer's architecture decision records, grouped by theme, with a one-sentence summary of what each one decides.
---

# Decision records

This page indexes every architecture decision record (ADR) in the Coffer repository and summarises, in one sentence each, what it decides. Read it when you want the *why* behind a part of the design, or before you propose a change that would reverse one of these choices.

## How decisions are recorded

Coffer keeps three kinds of design text, each with one job:

| Artefact | Lives in | Answers |
| --- | --- | --- |
| Specification | [`openspec/specs/<capability>/spec.md`](https://github.com/wyx-sg/Coffer/tree/main/openspec/specs) | *What* the product must do: requirements, each with scenarios that tests cover. |
| Change proposal | `openspec/changes/<change-id>/` | *How* one change is planned: `proposal.md`, `design.md`, `tasks.md` and spec deltas. |
| Decision record | [`docs/decisions/`](https://github.com/wyx-sg/Coffer/tree/main/docs/decisions) | *Why* a structural choice was made, and which alternatives lost. |

A decision earns a record when it is hard to reverse, constrains more than one module, carries a trade-off a future contributor will question, or departs from a convention or a [design principle](/architecture/design-principles). Library bumps, routine fixes and naming preferences do not.

Each record follows the Michael Nygard format — **Context**, **Decision**, **Consequences**, **Alternatives Considered** — under a header that states its **Status** (`Proposed`, `Accepted`, `Superseded by …` or `Deprecated`) and links related specs and records. Files are named by their title in kebab case, never by number, so a reference can never silently point at a different decision.

The directory records the **live** design rather than a chronological archive:

- When a decision changes, the record that owns it is rewritten, or amended with a marked note in place.
- When the thing a record decided is removed outright, the record is deleted. Git history (`git log --follow docs/decisions/`) is the archive.
- A superseded record stays only while it still explains a constraint the live design inherits.

::: tip
When a record says *Amended*, read the amendment as part of the decision. Where this index says "amended by", the summary already describes the amended decision.
:::

## Foundations

How the codebase and the product are shaped as a whole. See [Design principles](/architecture/design-principles) and [Layering and code layout](/architecture/layering).

| Record | Decision |
| --- | --- |
| [Resource Framework Designed Upfront](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/resource-framework-upfront.md) | The resource abstraction — kind-agnostic identity, lifecycle, audit and config validation, but not behaviour — is core domain, designed while only one kind existed rather than extracted once a second arrived. |
| [Code Layout — Layer-First with Kind Subdirectories](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/code-layout-layer-first.md) | The backend is organised by layer (`domain`, `application`, `infrastructure`, `surfaces`) with one subdirectory per kind inside each layer, not as vertical per-kind slices, and import-linter enforces the dependency direction. |
| [Information Architecture — Everything Is a Resource Kind](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/everything-is-a-resource-kind.md) | Every user-managed asset is a resource kind surfaced under one navigation model, consumers and cross-cutting tooling get their own role-based groups, and nothing appears in the sidebar until it works. |
| [Product Scope Is Settled](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/product-scope-is-settled.md) | The desktop shell, the web Chat page, bidirectional vault sync, the Activity page, and knowledge and memory as two kinds are settled scope; removing one requires amending this record. Amended by [Experimental Features Instead of a Release Branch](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/experimental-features-instead-of-a-release-branch.md): an experimental feature is off by default on `stable`, not removed. |

## Resources

Identity, reach and credentials shared by every kind. See [Resource framework](/architecture/resource-framework) and [Security model](/architecture/security).

| Record | Decision |
| --- | --- |
| [Resource Identity Is an Immutable `uid`, Not the Name](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/resource-identity-is-an-immutable-uid.md) | A resource is identified by an immutable `uid` and its name is a mutable label, so renaming never looks like delete-plus-create to sync, cascades or references. |
| [Resource Identifier Format — `<kind>:<name>`, Not URN](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/resource-identifier-format.md) | **Superseded by** [Resource Identity Is an Immutable `uid`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/resource-identity-is-an-immutable-uid.md); it made `<kind>:<name>` the external identifier, and is kept for the naming rules that still govern resource labels. |
| [Per-Agent Resource Scope](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/per-agent-resource-scope.md) | One framework-owned `scope` field — an allow-list of agent uids, where absent means every agent and empty means dormant — together with `enabled` forms a resource's *reach*, which is machine-local and never syncs; each kind enforces it at its own delivery point. |
| [Envelope-Encrypted Credential Store](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/envelope-encrypted-credential-store.md) | Secrets are stored as Fernet ciphertext in SQLite under one master key kept in a `0600` file by default, with the OS keychain as an opt-in location, so an unsigned binary never triggers keychain prompts. |

## MCP gateway

How Coffer aggregates upstream MCP servers behind one endpoint. See [MCP gateway](/architecture/mcp-gateway).

| Record | Decision |
| --- | --- |
| [One Upstream Subprocess Set Per Downstream Client Session](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/session-subprocess-model.md) | Each connected client session gets its own lazily spawned set of upstream subprocesses, reaped with the session, instead of sharing and multiplexing upstreams across clients. |
| [MCP Capability State — Preferences in DB, List Live-Queried From Upstream](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/capability-state-model.md) | The database stores only the user's enable/disable preference per tool, resource and prompt; the capability lists themselves are queried live from upstream and cached in memory for a short TTL. |
| [Tool Retrieval for Aggregation Overload](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tool-retrieval-for-overload.md) | Coffer exposes `coffer__search_tools`, a lexical (BM25-style) ranker over the whole aggregated catalogue, so an agent can find a tool by describing it. Amended by the two records below: ranking is lexical only, and the listed catalogue is tiered by the gateway. |
| [Budget-Driven Tool Tiering at the Gateway](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/budget-driven-tool-tiering.md) | The gateway lists a budgeted slice of upstream tools (50 by default) ranked by real invocation history, always lists Coffer's own tools, keeps at least one tool per server, and still lets any unlisted tool be called by name. |
| [Coffer Ships Its Own Manual as a Skill Resource](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/coffer-ships-its-own-skill.md) | Coffer's manual and knowledge catalogue ship as one built-in `coffer-guide` skill resource, regenerated from the running build, because a skill costs one resident description while the MCP handshake instructions are capped and charged to every session. |

## Daemon, desktop and web UI

The long-lived process and the surfaces that reach it. See [Daemon and processes](/architecture/daemon).

| Record | Decision |
| --- | --- |
| [Daemon Detect-or-Spawn Pattern](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-detect-or-spawn.md) | The daemon is an independent, resident process on a fixed loopback port (8000 unless configured); the CLI and the MCP shim read `~/.coffer/daemon.json`, connect to a live daemon or spawn a detached one, and authenticate with its token. |
| [The Daemon Serves Its Token in the Page, Guarded by the Host Header](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-serves-the-token-in-the-page.md) | The daemon injects its live API token into the `index.html` it serves, and refuses any request whose `Host` header is not a loopback authority, so a served page is authenticated without being open to DNS rebinding. |
| [The Desktop Shell Returns, Owning Only What a Browser Cannot Do](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/desktop-shell-over-a-shared-frontend.md) | A native Tauri shell hosts the same built frontend and owns exactly four things a browser cannot do: a window with a Dock icon, a resident tray, detect-or-spawn of the daemon at launch, and handing the page its daemon connection over IPC; it reimplements no daemon route. |
| [Local Daemon Proxies OS File Actions](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-proxies-os-file-actions.md) | Opening a file in an editor or revealing it in the file manager goes through daemon endpoints under the loopback and token guard, one mechanism for both the browser and the desktop shell. |

## Agents, chat and channels

How Coffer drives coding agents and reaches them from other surfaces. See [Chat and turns](/architecture/chat).

| Record | Decision |
| --- | --- |
| [The Built-in Agent Is an Internal Capability, Not a Chat Persona](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/builtin-agent-is-internal-capability.md) | Coffer's own model use is an internal auxiliary capability behind its tools and upkeep passes, not a user-facing chat agent; chat talks to managed agents only. |
| [Chat Is a Single-Owner Live Mirror](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/chat-single-owner-live-mirror.md) | The web Chat page is the browser view of the same conversations the owner drives from a phone: one agent session per conversation, observed live over a per-conversation event bus, interruptible, with queued messages. |
| [Remove the Tool-Approval System; Owner-Pairing Is the Gate](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/remove-tool-approval.md) | Driven agents run with full permissions and no per-tool approval, because every instruction comes from the paired owner and the approval relay added friction without safety. |
| [Provider Switching](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/provider-switching.md) | A provider connection is a credentialed endpoint with a protocol that Coffer projects into each agent's native config, keeping the API key in the vault and handing it over through a helper instead of writing plaintext; model and effort belong to the agent. |
| [Channel Adapter Framework](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-adapter-framework.md) | Channels are a resource kind whose thin per-platform adapters handle transport only, while pairing, the owner gate, commands and rendering live in a shared core that reaches agents through the chat platform's own seams. |
| [Channel Entrypoint Differentiation Layer](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-entrypoint-differentiation.md) | Switching agent from a channel opens a new conversation while switching model applies to the next turn, the chosen agent is sticky per thread, and channel turns run in Coffer's managed default workspace. |
| [Channel media — reference in the DB, materialise per agent at send](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-media.md) | Inbound attachment bytes are stored on disk outside the chat database and materialised per agent at send time: inline content blocks for Claude Code, file paths for Codex. Its "defer a persisted attachment block" clause is superseded by the next record. |
| [Persist channel attachments as a reference block, re-materialise from history](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/persisted-attachment-reference.md) | An attachment is persisted in the user message as a reference block (path, MIME type, filename — never bytes), and each turn re-materialises attachments from that persisted history. |
| [SeaTalk Inbound Over WebSocket, With an Operator-Supplied SDK](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/seatalk-websocket-inbound.md) | SeaTalk events arrive over one outbound WebSocket connection using an SDK the operator supplies, so Coffer needs no public endpoint, signature check or tunnel; without the SDK a channel can still send. |

## Knowledge and memory

What agents share beyond tools. See [Knowledge](/architecture/knowledge) and [Memory](/architecture/memory).

| Record | Decision |
| --- | --- |
| [One Shared Knowledge Store Across Agents](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-native-shared-memory.md) | Coffer holds one store shared by every agent rather than one per agent, so a project fact exists once instead of drifting between agents' private copies. |
| [The knowledge layer is a directory of files, not an index](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) | A collection is one Markdown tree that people and Coffer's internal model write together; new material lands in a hidden inbox that a curation pass merges into documents, agents read with their own file tools, and there is no derived index. |
| [Retrieval Stack — Markdown Files as Truth, Not a Vendored Engine](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/files-as-truth-sqlite-retrieval.md) | **Superseded by** [Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md); kept because it explains the import contract that still bans vendored retrieval and embedding engines from every layer. |
| [Aggregate the agents' memory; never write it](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/aggregate-agent-memory-never-write-it.md) | Coffer reads each agent's native memory read-only, distils it into its own one-topic-per-file notes partitioned by repository, and delivers the index of those notes at session start with the path to read them as files. |
| [Cross-Platform Skill Delivery — Symlink / Junction / Copy-Fallback](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/cross-platform-skill-delivery.md) | Each skill has one master folder in `~/.coffer/skills/`, delivered into every agent's skill directory as a symlink on POSIX or a junction on Windows, falling back to a copy only where links fail, with the link mode recorded. |

## Sync

Keeping one vault across a user's machines. See [Vault sync](/architecture/vault-sync).

| Record | Decision |
| --- | --- |
| [Vault Sync](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/vault-sync.md) | The vault converges with one git repository the user owns: each round commits the serialised vault, merges the remote with git's three-way merge as the only arbiter, applies the result and pushes, and the remote is a rendezvous that any single machine can rebuild. |

## Distribution and releases

How Coffer is built and shipped. See [Distribution and releases](/architecture/distribution).

| Record | Decision |
| --- | --- |
| [Distribution — PyInstaller-Bundled Daemon, Shim, and CLI](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/distribution-pyinstaller.md) | The daemon, the MCP shim and the CLI are frozen with PyInstaller into self-contained binaries, shipped from one release job as a terminal archive and inside the desktop `.dmg`, so users need no Python. |
| [Experimental Features Instead of a Release Branch](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/experimental-features-instead-of-a-release-branch.md) | `main` keeps every feature; unfinished ones are registered as experimental and switched off by default in `stable` builds, with a per-machine runtime switch stored in `~/.coffer/daemon-config.json` that never syncs. |

## Engineering harness

How Coffer itself is built and verified, by humans and coding agents. See [Contributing](/contributing/).

| Record | Decision |
| --- | --- |
| [Industrial-Grade Harness, Built in Layers](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/industrial-grade-harness-in-layers.md) | The engineering and agent-facing harness is built in independent layers — agent permissions and hooks, a reproducible environment, smoke checks and evals. Status: the agent-control layer, the eval layer and the committed lockfile are in place; the devcontainer, per-branch database and smoke layer were not built. |
| [Close the Eval Flywheel (Loop Engineering)](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/close-the-eval-flywheel.md) | Coffer's non-deterministic behaviour gets a closed quality loop — an honest invocation log, an opt-in local capture sink, curation into golden cases, and an eval gate — built as independently shippable slices. |

## Related

- [Architecture overview](/architecture/)
- [Design principles](/architecture/design-principles)
- [Spec-driven workflow](/contributing/spec-workflow)
- [All decision records on GitHub](https://github.com/wyx-sg/Coffer/tree/main/docs/decisions)
