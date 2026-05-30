# Getting Started

> **This page covers the from-source / developer path.** For a prebuilt one-line install or
> the Desktop app, see [Download & install](/guide/install).

Install Coffer from source and connect your first MCP client. Once the daemon is running, every
MCP client on your machine can connect through the shim without any additional configuration.

## Install from source

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
make verify          # sanity-check the install
```

`pip install` puts both the CLI (`coffer`) and the stdio shim (`coffer-mcp-shim`) on your `PATH`
as console-script entry points — no separate deploy step.

- **`coffer`** — the management CLI for registering and inspecting MCP servers.
- **`coffer-mcp-shim`** — the stdio bridge that MCP clients use to talk to the daemon.

`make verify` runs the full check suite (lint, type, unit, integration, contract, acceptance audit)
to confirm the install is healthy.

::: tip Daemon auto-starts — no manual start required
The daemon spawns automatically the first time you run any `coffer` management command or an MCP
client connects through the shim. `coffer daemon start` exists for explicit control but is **not**
a required setup step.
:::

[Register your first server →](/guide/register-server)
