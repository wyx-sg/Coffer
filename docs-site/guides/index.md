---
title: Guides
description: Every task-oriented guide to Coffer in one place, grouped by what you came to do — connect agents and tools, share skills, knowledge and memory, talk to agents, use the apps and operate Coffer.
---

# Guides

One page per task. Each guide shows the CLI command and the place in the app. They assume Coffer is installed and the daemon is running. If it is not, start with [Install](/start/install) and the [Quickstart](/start/quickstart); for the vocabulary the guides use, read [Core concepts](/start/concepts).

## Agents and tools

<LinkList :items="[
{ title: 'Agents', desc: 'Register Claude Code and Codex and look after their config.', link: '/guides/agents' },
{ title: 'Connect a client', desc: 'Wire an agent to Coffer through one entry.', link: '/guides/connect-a-client' },
{ title: 'MCP servers', desc: 'Register upstream servers once for every agent.', link: '/guides/mcp-servers' },
{ title: 'Custom tools', desc: 'Turn an HTTP API into tools.', link: '/guides/custom-tools' },
{ title: 'Model providers', desc: 'Store a provider and switch agents to it.', link: '/guides/providers' },
{ title: 'Usage and quota', desc: 'See what agents spent and what quota is left.', link: '/guides/usage' },
{ title: 'Secret store', desc: 'How secrets are encrypted and where the key lives.', link: '/guides/secret-store' },
{ title: 'Secrets', desc: 'Keep keys encrypted and out of agent config.', link: '/guides/secrets' }
]" />

## What agents share

<LinkList :items="[
{ title: 'Skills', desc: 'Import a skill library and deliver it.', link: '/guides/skills' },
{ title: 'CLIs', desc: 'Find missing command-line tools and hand the fix to your agent.', link: '/guides/clis' },
{ title: 'Writing skill libraries', desc: 'Structure skills that travel between agents.', link: '/guides/writing-skill-libraries' },
{ title: 'Knowledge', desc: 'Markdown every agent reads and adds to.', link: '/guides/knowledge' },
{ title: 'Memory', desc: 'Share what each agent learns.', link: '/guides/memory' }
]" />

## Talking to agents

<LinkList :items="[
{ title: 'Conversations', desc: 'Drive an agent from the browser.', link: '/guides/chat' },
{ title: 'Channels', desc: 'Chat with your agents from Telegram or SeaTalk.', link: '/guides/channels' },
{ title: 'Telegram', desc: 'Pair a Telegram bot.', link: '/guides/channels-telegram' },
{ title: 'SeaTalk', desc: 'Pair a SeaTalk bot.', link: '/guides/channels-seatalk' }
]" />

## Apps

<LinkList :items="[
{ title: 'Web UI', desc: 'Open the UI in a browser.', link: '/guides/web-ui' },
{ title: 'Desktop app', desc: 'The menu bar, updates and restarts.', link: '/guides/desktop-app' }
]" />

## Operating Coffer

<LinkList :items="[
{ title: 'Running the daemon', desc: 'Start, stop and check the daemon.', link: '/guides/daemon' },
{ title: 'Editing the vault by hand', desc: 'Edit the vault\'s plain files and restore any version.', link: '/guides/vault-files' },
{ title: 'Vault sync', desc: 'Keep the vault on every Mac through git.', link: '/guides/vault-sync' },
{ title: 'Upgrading an existing Coffer', desc: 'Move an older Coffer home into the vault layout.', link: '/guides/upgrading' },
{ title: 'Activity and audit', desc: 'See what changed and every tool call.', link: '/guides/activity' },
{ title: 'Experimental features', desc: 'Switch capabilities that are not ready yet.', link: '/guides/experimental-features' },
{ title: 'Troubleshooting', desc: 'Fix the common failures.', link: '/guides/troubleshooting' },
{ title: 'FAQ', desc: 'Short answers to common questions.', link: '/guides/faq' }
]" />
