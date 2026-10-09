---
title: Why Coffer
description: The design decisions behind Coffer (local-first, agent files as the source of truth, one MCP endpoint, pull-based knowledge, encrypted secrets, git sync you own) and what each one means for you.
---

# Why Coffer

This page explains the decisions that shape Coffer, for readers deciding whether to adopt it. Each section gives the decision, the reason for it, and what it means for you in practice. The [design principles](/architecture/design-principles) page covers the same ground in more depth.

## Local-first

**The decision.** All of Coffer's state lives on your machine, in `~/.coffer`. The daemon's HTTP API and MCP endpoint bind to `127.0.0.1` and reject any request whose `Host` header is not loopback. Cloud services are only ever providers: the models and MCP servers you choose to call. None of them is where your vault is stored.

**Why.** The things agents accumulate are yours: tools, skills, notes, and API keys. If a hosted service held them, you would need an account, a network connection and trust in a third party just to open your own configuration. A process on loopback needs none of these.

**What it means for you.**

- There is no sign-up, and Coffer works offline apart from any upstream servers or models you use.
- Backing up means copying one directory. Stop the daemon, then run `cp -r ~/.coffer <backup>`.
- Nothing on your network can reach the daemon. Only processes on this machine that can read `~/.coffer/daemon.json` (mode `0600`) get the API token.

## The agent's own files stay the source of truth

**The decision.** Coffer never copies an agent's configuration, MCP entries, plugins or transcripts into its own store. It reads them from the agent's files each time it needs them. When Coffer writes, it writes only documented, allowlisted entries: its own `coffer` MCP entry, a config file you edit in the UI, a plugin switch, and, with memory sync on, its own copies of your other agents' memories. Each write is atomic and first copies the previous version to `~/.coffer/config-backups`, outside the agent's directory. Codex's TOML is edited in a way that keeps your comments and ordering.

**Why.** A second copy of an agent's settings goes stale the moment you edit the original, and then someone has to decide which copy wins. Reading from the original means there is nothing to reconcile.

**What it means for you.**

- You can keep editing `~/.claude/settings.json` or `~/.codex/config.toml` by hand, and Coffer shows your changes straight away.
- Removing Coffer leaves your agents working. Uninstall Coffer's MCP entry and the agents go back to their own configuration.
- Coffer never edits a memory an agent wrote. When memory sync is on, it adds only files of its own beside the agent's memories, and **Undo sync** removes them.

## One MCP endpoint instead of one config per agent

**The decision.** Each agent's MCP config holds one entry, `coffer`, which runs `coffer-mcp-shim`. Coffer runs every upstream server you register and lists their tools under a `<server>__<tool>` prefix, so two servers can both have a `search` tool without clashing. You decide which tools a server exposes, and which agents can see it, in Coffer rather than in each agent.

**Why.** With N agents and M servers you would otherwise maintain N×M entries by hand. One endpoint turns that into M registrations. It also gives Coffer a single point where it can apply per-agent scope and record every call (which tool, when, how long, the outcome, and its arguments and result with secrets masked).

**What it means for you.**

- Register a server once on the **MCP servers** page. Every agent with Coffer installed gets its tools in its next session.
- Once the catalogue grows past a budget (50 upstream tools by default), `tools/list` shows only the most-used tools. The built-in `coffer__search_tools` tool searches the full catalogue, and every tool can still be called.
- Each agent session gets its own upstream subprocesses, so two agents working at the same time do not interfere with each other.

See [MCP gateway](/architecture/mcp-gateway) for how sessions, namespacing and tool tiering work.

## Knowledge is pulled, not pushed

**The decision.** Coffer does not insert knowledge into an agent's prompt. A knowledge collection is a folder of Markdown files under `~/.coffer/vault/knowledge/`. Coffer delivers one skill of its own, `coffer-guide`, which lists every collection's documents with their paths, titles and descriptions. The agent reads what it needs with its own `Read` and `Grep` tools. Coffer does not index, chunk or embed the files.

**Why.** Retrieval that depends on the agent remembering to call a special tool gets skipped. Every supported agent can already read files. What an agent needs is to know which files exist and where they are, and a catalogue gives it that. Keeping the files as the only copy also means you can edit a document in your own editor and the next read picks up the change.

**What it means for you.**

- Your knowledge is plain Markdown you can open, grep, version and edit in any tool.
- Agents add knowledge by writing a Markdown document straight into a collection, and change one by editing it. The `coffer-guide` skill tells them where a fact belongs. When a collection gets cluttered, press **Tidy** and your default agent merges, splits and corrects its documents.
- Memory works the other way round. Coffer writes what one agent learned into your other agents' own memory, on every machine you sync, and each agent loads and curates it like its own. The [memory guide](/guides/memory) explains how.

## Secrets are encrypted with a key you hold

**The decision.** Secrets are stored only as Fernet ciphertext, one file per secret under `~/.coffer/vault/secret/`. Configuration never holds a secret; it holds a *secret ref*, a name such as `github.token`. The daemon decrypts the secret only at the moment it starts an upstream server or sends a request header. The master key is one item in the macOS Keychain that only Coffer's signed binaries can read, and it never enters the vault.

**Why.** MCP server configs and provider profiles need API keys. If keys were stored as plain text, every export, log line and sync commit would put them at risk. With refs, the rest of the system never handles the plaintext.

**What it means for you.**

- Store a secret with `coffer secret set <ref>`, which prompts for the value without echoing it or reads it from stdin, and refer to it by name everywhere else.
- Plaintext never reaches the vault, the logs or the audit log.
- If you lose the master key, you lose every stored secret. The Keychain is the key's only home, so back it up in the desktop app and keep the backup the way you would keep an SSH private key.

See [Security model](/architecture/security) for the full threat model.

## Sync goes through a git remote you own

**The decision.** To share one vault between your machines, point each of them at a git repository you own. Sync is off until you set it up. The vault is already a git repository, so a background worker only fetches, lets git merge, and pushes. A clean merge is applied; any conflict stops the round, with nothing changed on either side, until you choose per file. A round that would delete more than a set share of the vault stops and asks you first, and every round can be rolled back. Secrets travel only as ciphertext. The master key moves between machines only when you carry the key yourself: the desktop app writes a backup, and **Settings › Security › Import a master key** installs it.

**Why.** A service run by Coffer would break the local-first rule. A git remote under your control is a meeting point, not a system of record: every machine keeps the complete vault, so you can delete the remote and rebuild it from any single machine.

**What it means for you.**

- You choose the host (GitHub, GitLab, your own server) and can read every commit Coffer makes.
- Some settings stay on each machine. A resource's *reach* (whether it is enabled here, and which agents may use it) does not sync, so each machine decides for itself.
- A new machine joins from the **Sync** page. It shows what joining would do, deletes nothing, and asks you before applying it.

See [Vault sync](/architecture/vault-sync) for the round in detail.

## Related

- [Design principles](/architecture/design-principles)
- [Architecture overview](/architecture/)
- [Decision records](/architecture/decisions)
- [Core concepts](/start/concepts)
