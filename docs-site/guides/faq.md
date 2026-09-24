---
title: FAQ
description: Short answers to common questions about Coffer — privacy, supported agents and platforms, models, cost, multiple machines, where data lives, and uninstalling.
---

# FAQ

Short answers to the questions people ask most before and after installing Coffer, with links to the page that covers each topic in depth.

## Does anything leave my machine?

Not by Coffer's own doing, unless you configure it to. The daemon listens only on `127.0.0.1`, has no telemetry, and keeps its state under `~/.coffer`. Network traffic happens only through things you set up:

- **MCP servers you register.** Coffer starts a stdio server and connects to an HTTP server at the URL you gave; what they contact is up to each server.
- **Model providers.** If you choose a provider for **Coffer's model** or **Speech to text**, Coffer sends those requests to it. Your agents talk to their own providers as they always do.
- **Vault sync.** If you configure a remote, rounds push to and pull from that git repository. Credentials travel only as ciphertext and only if you opt in; the master key never does.
- **Channels.** A Telegram or SeaTalk channel exchanges messages with that platform.

The endpoints you configure as your own — an HTTP MCP server, a model or transcription endpoint, a sync remote — may be on your own machine or network. A URL Coffer only probes on your behalf while you fill in a form (**Test connection** and model listing in the provider editor) is refused if it resolves to a loopback, private or link-local address, unless the provider is an Ollama server.

See [Security model](/architecture/security).

## Which agents does Coffer support?

Coffer manages **Claude Code** and **Codex**: it detects them, installs its MCP entry into them, delivers skills and memory, projects model providers into their configuration, and can run them from [Chat](/guides/chat) and [Channels](/guides/channels).

Any other MCP client that can launch a stdio server can still use Coffer's gateway by running `coffer-mcp-shim`. Such a session reports no agent identity, so it sees only servers whose reach is not restricted to particular agents. See [Connect a client](/guides/connect-a-client).

## Can I use it on Linux or Windows?

Releases, the one-line installer and the desktop app are built for **macOS on Apple silicon** only. Other platforms are not built or tested. Starting the daemon at login is macOS-only as well. See [Install](/start/install).

## Does Coffer run a language model?

No model runs inside Coffer. A few of Coffer's own background passes need one (merging new knowledge into documents, distilling memory, describing knowledge collections, transcribing voice messages, resolving a sync conflict), and they call a model provider you pick under **Settings → Coffer's model**. Until you pick one, curation and distillation run mechanically (each new item becomes a document or note as it stands), sync conflicts wait for you, and voice messages reach the agent as audio files.

Everything else is deterministic and local. `coffer__search_tools` ranks tools by keyword, agents find knowledge with their own file tools, `coffer__recall` is a literal match, and nothing is embedded. See [Model providers](/guides/providers).

## What does it cost?

Coffer is free and open source under the MIT license. The only costs are the ones you already have: the model providers your agents and Coffer's own passes call, and any hosting for a sync remote you choose.

## How is this different from listing MCP servers in each agent's config?

With per-agent configuration you register, update and secure every server once per agent. With Coffer:

- you register a server once, and every agent reaches it through one MCP entry;
- its secrets are encrypted in Coffer's store instead of sitting in plain-text agent config files;
- you choose per server which agents may use it, and switch individual tools off;
- tool names are namespaced by server (`github__search`), so two servers never collide;
- every call is recorded (without its arguments) for [Activity](/guides/activity);
- a large catalogue is listed within a budget, and agents find the rest with `coffer__search_tools`.

Skills, knowledge, memory and model providers work the same way: kept once, delivered to every agent. See [Why Coffer](/start/why-coffer).

## Does Coffer change my agents' configuration files?

Only when you ask it to, and each change is recorded in the audit log. Installing Coffer's MCP entry writes one server entry into the agent's configuration. Delivering a skill places a link to it in the agent's skills directory (for Claude Code, `~/.claude/skills`). Switching a model provider writes the provider's settings into the agent's own configuration. Installing memory delivery (`coffer memory delivery-install <agent>`) adds a session-start hook to the agent's settings. Coffer reads an agent's own memory files but never writes them. See [Agents](/guides/agents).

## Do I have to start the daemon myself?

No. Any `coffer` command that needs the daemon, an agent connecting through `coffer-mcp-shim`, and the desktop app all start the daemon if it is not running. `coffer daemon status` is the exception: it only reports, and says `not running` instead of starting one. On macOS, `coffer daemon service install` starts it at login and restarts it after a crash. See [Running the daemon](/guides/daemon).

## Where is my data?

In `~/.coffer` on each machine:

| Path | Contents |
| --- | --- |
| `coffer.db` | Resources, settings, encrypted credentials, conversations, audit and invocation logs |
| `master.key` | The key that decrypts credentials (unless moved to the OS keychain) |
| `knowledge/` | Knowledge collections, as plain Markdown |
| `skills/` | The master skill store |
| `memory/` | Memory derived from your agents' own stores |
| `logs/` | Daemon, shim and MCP server logs |
| `bin/` | Deployed binaries (release installs) |

The complete list is in [Files and directories](/reference/filesystem).

## How are my secrets stored?

Credentials are encrypted with Fernet in `coffer.db`. The master key lives in `~/.coffer/master.key` (mode `0600`) by default, or in the macOS keychain if you opt in under **Settings → Security**. Resources name a credential by reference, never by value. See [Credentials](/guides/credentials).

## Can two machines share one vault?

Yes, through [vault sync](/guides/vault-sync), an experimental feature. Each machine converges with a private git repository you own. Knowledge, skills and resource definitions travel. Reach (whether a resource is enabled on a machine, and for which agents), conversations and logs stay on each machine.

## Can I open the web UI from my phone or another computer?

No. The daemon binds to loopback only, so its UI and API are reachable from the machine they run on and nowhere else. To reach your agents from a phone, use a [channel](/guides/channels): Telegram or SeaTalk.

## Why are Sync, Knowledge and Memory missing?

They are [experimental features](/guides/experimental-features), switched off by default in release builds. Turn them on under **Settings → General → Experimental features**, or with `coffer daemon features enable <key>`. Switching one off never deletes what it holds.

## Why port 8000, and can I change it?

A fixed port keeps bookmarks working and keeps the browser's stored preferences for the UI. Change it with `coffer daemon port set <port>`, then `coffer daemon restart`. See [Choose the port](/guides/daemon#choose-the-port).

## How do I upgrade?

Install the new version the same way you installed the old one, then run `coffer daemon restart` so the running daemon is replaced. Until you do, commands print a version warning. The previous build stays in `~/.coffer/bin` for a rollback, and the database is copied before any migration. See [Upgrades and rollback](/guides/daemon#upgrades-and-rollback).

## How do I uninstall Coffer?

Remove Coffer's MCP entry and memory hook from each agent, unregister the agents (which removes the skill links Coffer delivered), stop the daemon and its login service, then delete the binaries and, if you want, `~/.coffer`. [Install → Uninstall](/start/install#uninstall) gives the exact commands. Back up `~/.coffer`, including `master.key`, first if you might want it again.

If you used vault sync, the remote repository is untouched and still holds your vault's documents.

## Where do I report a bug?

On [GitHub Issues](https://github.com/wyx-sg/Coffer/issues). [Troubleshooting](/guides/troubleshooting#collect-information-for-a-bug-report) lists what to include. Report security problems privately, as described in the [security policy](/contributing/security).
