# Coffer

**English** · [简体中文](./README.zh-CN.md)

<p align="center">
  <a href="https://wyx-sg.github.io/Coffer/"><img alt="Docs" src="https://img.shields.io/badge/docs-coffer-4353D8"></a>
  <a href="./LICENSE"><img alt="License: AGPL-3.0" src="https://img.shields.io/badge/license-AGPL--3.0-blue"></a>
  <img alt="Platform: macOS" src="https://img.shields.io/badge/platform-macOS-555">
</p>

> A local-first vault for your AI coding agents. Set up MCP servers, skills, knowledge, memory and model providers once, and every agent on your machine shares them.

Coffer is one daemon on your machine that your coding agents connect to (today Claude Code and Codex). It keeps what they share in plain files under `~/.coffer` and delivers it into each agent. You manage it from a web UI, a macOS desktop app, or a chat channel on your phone. No account, no cloud backend: the daemon listens on `127.0.0.1` only.

📖 **Documentation:** <https://wyx-sg.github.io/Coffer/> ([中文](https://wyx-sg.github.io/Coffer/zh/))

## What it does

- **One MCP endpoint** for every agent, with per-agent reach and a call log.
- **One skill library**, linked into each agent and kept up to date.
- **Knowledge and memory** as plain files every agent reads.
- **Model providers** behind a local proxy that holds the keys and meters usage.
- **Secrets** stored encrypted; agents use them without ever holding them.
- **Chat channels and conversations** to drive your agents from your phone, then pick the session up in your terminal.
- **Vault sync** across your machines through a git remote you own.

## Install

**Requirements:** git 2.40 or later; a coding agent to connect (Claude Code or Codex). Prebuilt builds are for macOS on Apple silicon; elsewhere, install from source (Python 3.12+, Node.js 20). ripgrep is optional. See [Requirements](https://wyx-sg.github.io/Coffer/start/install#requirements).

Paste this into a coding agent that can run commands on your machine:

```text
Install Coffer on this machine by following
https://wyx-sg.github.io/Coffer/start/install — pick the install path that fits
this machine. Ask me before running anything with sudo or editing my shell
profile. When it is installed, check it with `coffer daemon status`, then tell me
which coding agents it found here. Do not handle any credentials: if a step needs
a login, tell me what to do instead.
```

Or follow the [install guide](https://wyx-sg.github.io/Coffer/start/install) yourself.

## Contributing

[`AGENTS.md`](./AGENTS.md) is the operating manual and [Contributing](https://wyx-sg.github.io/Coffer/contributing/) the guide; `make verify` is the gate a change must pass. Report security issues privately, as the [security policy](./SECURITY.md) describes.

## License

Copyright © 2026 Asen. Coffer is free software under the [GNU Affero General Public License v3.0 or later](./LICENSE): you may use, change and redistribute it, and anything you distribute or offer over a network that is built on it must be released under the same licence, with its source.
