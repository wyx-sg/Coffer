---
title: Guides
description: Every task-oriented guide to Coffer in one place, grouped by what you came to do — connect agents and tools, share skills, knowledge and memory, talk to agents, use the apps and operate Coffer.
---

# Guides

One page per task. Each guide shows the place in the app, and a command where an agent or a script is likely to want one; every action in the app has a `coffer` command, listed in [CLI coverage](/reference/cli-coverage). They assume Coffer is installed and the daemon is running. If it is not, start with [Install](/start/install) and the [Quickstart](/start/quickstart); for the vocabulary the guides use, read [Core concepts](/start/concepts).

## Agents and tools

<LinkList>

- [Agents](/guides/agents) Register Claude Code and Codex and look after their config.
- [Connect a client](/guides/connect-a-client) Wire an agent to Coffer through one entry.
- [MCP servers](/guides/mcp-servers) Register upstream servers once for every agent.
- [Custom tools](/guides/custom-tools) Turn an HTTP API into tools.
- [Model providers](/guides/providers) Store a provider and switch agents to it.
- [Usage](/guides/usage) See what requests through your providers cost, by model, agent or day.
- [Secret store](/guides/secret-store) How secrets are encrypted and where the key lives.
- [Secrets](/guides/secrets) Keep keys encrypted and out of agent config.

</LinkList>

## What agents share

<LinkList>

- [Skills](/guides/skills) Import a skill library and deliver it.
- [CLIs](/guides/clis) Find missing command-line tools and hand the fix to your agent.
- [Writing skill libraries](/guides/writing-skill-libraries) Structure skills that travel between agents.
- [Knowledge](/guides/knowledge) Markdown every agent reads and adds to.
- [Memory](/guides/memory) Share what each agent learns.

</LinkList>

## Talking to agents

<LinkList>

- [Conversations](/guides/chat) Drive an agent from the browser.
- [Channels](/guides/channels) Chat with your agents from Telegram or SeaTalk.
- [Telegram](/guides/channels-telegram) Pair a Telegram bot.
- [SeaTalk](/guides/channels-seatalk) Pair a SeaTalk bot.

</LinkList>

## Apps

<LinkList>

- [Web UI](/guides/web-ui) Open the UI in a browser.
- [Desktop app](/guides/desktop-app) The menu bar, updates and restarts.

</LinkList>

## Operating Coffer

<LinkList>

- [Running the daemon](/guides/daemon) Start, stop and check the daemon.
- [Editing the vault by hand](/guides/vault-files) Edit the vault\'s plain files and bring back an earlier version through git or your agent.
- [Vault sync](/guides/vault-sync) Keep the vault on every Mac through git.
- [Activity and audit](/guides/activity) See what changed and every tool call.
- [Experimental features](/guides/experimental-features) Switch capabilities that are not ready yet.
- [Troubleshooting](/guides/troubleshooting) Fix the common failures.
- [FAQ](/guides/faq) Short answers to common questions.

</LinkList>
