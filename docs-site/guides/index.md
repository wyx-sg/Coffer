---
title: Guides
description: Every task-oriented guide to Coffer in one place, grouped by what you came to do — connect agents and tools, share skills, knowledge and memory, talk to agents, use the apps and operate Coffer.
---

# Guides

Each guide walks you through one task end to end: what to run or click, what Coffer does in response, and how to check it worked. They assume Coffer is installed and the daemon is running. If it is not, start with [Install](/start/install) and the [Quickstart](/start/quickstart); for the vocabulary the guides use, read [Core concepts](/start/concepts).

## Agents and tools

- [Agents](/guides/agents): register Claude Code and Codex, connect them to Coffer, and manage their config files, MCP entries, plugins, hooks, models, memory and transcripts.
- [Connect a client](/guides/connect-a-client): point Claude Code, Codex or any other MCP client at Coffer's gateway, and verify the connection.
- [MCP servers](/guides/mcp-servers): register upstream MCP servers once, curate their tools, choose which agents reach them, and read the invocation log.
- [Custom tools](/guides/custom-tools): turn an HTTP API into tools your agents call, from an OpenAPI spec or one request defined by hand.
- [Model providers](/guides/providers): store a model endpoint and its key once, switch agents onto it, and choose the model Coffer's own engine runs on.
- [Usage and quota](/guides/usage): what your agents spent on API-key and local providers, and how much of a subscription's allowance is left.
- [Secret store](/guides/secret-store): how Coffer encrypts every secret, where the master key lives, and how to back it up or carry it to another machine.
- [Secrets](/guides/secrets): the Secrets page, standalone secrets, `coffer run`, approvals, and moving plaintext files into the store.

## What agents share

- [Skills](/guides/skills): keep one library of AgentSkills folders and deliver each one into the agents you choose.
- [CLIs](/guides/clis): see which command-line tools your skills and MCP servers need are missing, too old or not logged in, and hand the fix to your agent.
- [Writing skill libraries](/guides/writing-skill-libraries): structure a library so one skill body serves every organisation.
- [Knowledge](/guides/knowledge): keep what you and your agents know as folders of Markdown that every agent reads with its own file tools.
- [Memory](/guides/memory): let Coffer distil what each agent has learned into one set of notes per repository and hand them back at the right moments.

## Talking to agents

- [Conversations](/guides/chat): talk to Claude Code or Codex from the web Conversations page, and watch or continue conversations started from a channel.
- [Channels](/guides/channels): connect a Telegram bot or SeaTalk app, pair it to your account, and drive your agents from the IM app you already use.
- [Telegram](/guides/channels-telegram) and [SeaTalk](/guides/channels-seatalk): the setup steps for each channel.

## Apps

- [Web UI](/guides/web-ui): how the web UI is served and signed in, and how its sidebar, command palette and Settings window are laid out.
- [Desktop app](/guides/desktop-app): the macOS app, the only place a secret is revealed, the master key is backed up or an approval is given.

## Operating Coffer

- [Running the daemon](/guides/daemon): start, stop and supervise the daemon, pin its port, run it at login, and back up a vault.
- [Editing the vault by hand](/guides/vault-files): edit the vault's plain files in any editor, and read, compare and restore any version.
- [Vault sync](/guides/vault-sync): keep one vault across several machines through a private git remote you own.
- [Upgrading an existing Coffer](/guides/upgrading): move an older Coffer home into the vault layout with `coffer migrate`.
- [Activity and audit](/guides/activity): read what changed, what agents called and what the daemon logged, and control how long each record is kept.
- [Experimental features](/guides/experimental-features): how a capability that is not ready yet ships, and how to switch it per machine.
- [Troubleshooting](/guides/troubleshooting) and [FAQ](/guides/faq): symptoms and fixes for common problems, and short answers to common questions.
